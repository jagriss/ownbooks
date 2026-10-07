-- Applies seeds/merchant_rules.csv: each transaction takes the
-- lowest-priority-number rule whose ILIKE pattern matches its
-- clean_description (longer patterns win ties, being more specific).
-- No match leaves it 'Uncategorized', which surfaces it in
-- mart_uncategorized for a rule to be written.

WITH cleaned AS (

    SELECT *
    FROM {{ ref('int_transactions__cleaned') }}

),

rules AS (

    SELECT *
    FROM {{ ref('merchant_rules') }}

),

matched AS (

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

)

SELECT
    * EXCLUDE (rule_merchant_name, rule_category),
    coalesce(rule_merchant_name, clean_description) AS merchant_name,
    coalesce(rule_category, 'Uncategorized') AS category
FROM matched
