-- Assigns each transaction a category from the first source that
-- applies:
--   1. rule: the lowest-priority-number pattern in
--      seeds/merchant_rules.csv matching clean_description (longer
--      patterns win ties, being more specific);
--   2. bank: the bank's own category, mapped through
--      seeds/bank_category_map.csv (longest pattern wins);
--   3. none: 'Uncategorized'.
-- A rule overrides a bank guess, and anything without a rule appears
-- in mart_uncategorized.

WITH cleaned AS (
    SELECT
        txn_id
        ,account_key
        ,institution
        ,txn_date
        ,description
        ,raw_description
        ,amount
        ,bank_type
        ,bank_category
        ,source_file
        ,extracted_at
        ,clean_description
    FROM {{ ref('int_transactions__cleaned') }}
)

,rules AS (
    SELECT
        pattern
        ,merchant_name
        ,category
        ,priority
    FROM {{ ref('merchant_rules') }}
)

,bank_map AS (
    SELECT
        institution
        ,bank_category
        ,category
    FROM {{ ref('bank_category_map') }}
)

,rule_matched AS (
    SELECT
        cleaned.txn_id
        ,cleaned.account_key
        ,cleaned.institution
        ,cleaned.txn_date
        ,cleaned.description
        ,cleaned.raw_description
        ,cleaned.amount
        ,cleaned.bank_type
        ,cleaned.bank_category
        ,cleaned.source_file
        ,cleaned.extracted_at
        ,cleaned.clean_description
        ,rules.merchant_name AS rule_merchant_name
        ,rules.category AS rule_category
        ,rules.pattern AS matched_pattern
    FROM cleaned
    LEFT JOIN rules
        ON cleaned.clean_description ILIKE rules.pattern
    QUALIFY row_number() OVER (
        PARTITION BY cleaned.txn_id
        ORDER BY rules.priority ASC, length(rules.pattern) DESC
    ) = 1
)

,bank_matched AS (
    SELECT
        rule_matched.txn_id
        ,rule_matched.account_key
        ,rule_matched.institution
        ,rule_matched.txn_date
        ,rule_matched.description
        ,rule_matched.raw_description
        ,rule_matched.amount
        ,rule_matched.bank_type
        ,rule_matched.bank_category
        ,rule_matched.source_file
        ,rule_matched.extracted_at
        ,rule_matched.clean_description
        ,rule_matched.rule_merchant_name
        ,rule_matched.rule_category
        ,rule_matched.matched_pattern
        ,bank_map.category AS bank_mapped_category
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

,assigned AS (
    SELECT
        txn_id
        ,account_key
        ,institution
        ,txn_date
        ,description
        ,raw_description
        ,amount
        ,bank_type
        ,bank_category
        ,source_file
        ,extracted_at
        ,clean_description
        ,matched_pattern
        ,coalesce(rule_merchant_name, clean_description) AS merchant_name
        ,coalesce(rule_category, bank_mapped_category, 'Uncategorized')
            AS category
        ,CASE
            WHEN rule_category IS NOT NULL THEN 'rule'
            WHEN bank_mapped_category IS NOT NULL THEN 'bank'
            ELSE 'none'
        END AS category_source
    FROM bank_matched
)

,final AS (
    SELECT
        txn_id
        ,account_key
        ,institution
        ,txn_date
        ,description
        ,raw_description
        ,amount
        ,bank_type
        ,bank_category
        ,source_file
        ,extracted_at
        ,clean_description
        ,matched_pattern
        ,merchant_name
        ,category
        ,category_source
    FROM assigned
)

SELECT
*
FROM final
