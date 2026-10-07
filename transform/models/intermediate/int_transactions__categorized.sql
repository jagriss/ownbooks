-- Assigns each transaction a category, first source that applies:
--   1. rule  -- the lowest-priority-number pattern in
--               seeds/merchant_rules.csv matching clean_description
--               (longer patterns win ties, being more specific);
--   2. bank  -- the bank's own category, mapped through
--               seeds/bank_category_map.csv (longest pattern wins);
--   3. none  -- 'Uncategorized'.
-- Rules always win, so a bank guess is overridden by writing a rule;
-- anything without one surfaces in mart_uncategorized.

WITH cleaned AS (

    SELECT *
    FROM {{ ref('int_transactions__cleaned') }}

),

rules AS (

    SELECT *
    FROM {{ ref('merchant_rules') }}

),

bank_map AS (

    SELECT *
    FROM {{ ref('bank_category_map') }}

),

rule_matched AS (

    SELECT
        cleaned.*,
        rules.merchant_name AS rule_merchant_name,
        rules.category AS rule_category,
        rules.pattern AS matched_pattern
    FROM cleaned
    LEFT JOIN rules
        ON cleaned.clean_description ILIKE rules.pattern
    QUALIFY row_number() OVER (
        PARTITION BY cleaned.txn_id
        ORDER BY rules.priority ASC, length(rules.pattern) DESC
    ) = 1

),

bank_matched AS (

    SELECT
        rule_matched.*,
        bank_map.category AS bank_mapped_category
    FROM rule_matched
    LEFT JOIN bank_map
        ON
            rule_matched.institution = bank_map.institution
            AND rule_matched.bank_category ILIKE bank_map.bank_category
    QUALIFY row_number() OVER (
        PARTITION BY rule_matched.txn_id
        ORDER BY length(bank_map.bank_category) DESC
    ) = 1

)

SELECT
    * EXCLUDE (rule_merchant_name, rule_category, bank_mapped_category),
    coalesce(rule_merchant_name, clean_description) AS merchant_name,
    coalesce(rule_category, bank_mapped_category, 'Uncategorized')
        AS category,
    CASE
        WHEN rule_category IS NOT NULL THEN 'rule'
        WHEN bank_mapped_category IS NOT NULL THEN 'bank'
        ELSE 'none'
    END AS category_source
FROM bank_matched
