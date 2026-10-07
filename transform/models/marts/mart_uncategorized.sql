-- The categorization to-do list: descriptions no merchant rule covers.
-- Includes ones categorized only by the bank's own category
-- (category_source = 'bank'), with that guess shown, so they can be
-- confirmed or corrected by writing a rule.

WITH transactions AS (
    SELECT
        clean_description
        ,raw_description
        ,amount
        ,txn_date
        ,category
        ,category_source
        ,account_key
    FROM {{ ref('fct_transactions') }}
    WHERE category_source != 'rule'
)

,by_description AS (
    SELECT
        clean_description
        ,count(*) AS txn_count
        ,sum(amount) AS total_amount
        ,min(txn_date) AS first_seen
        ,max(txn_date) AS last_seen
        -- The bank-derived guess, if any of its transactions have one.
        ,mode(category) FILTER (WHERE category_source = 'bank') AS bank_guess
        ,count(*) FILTER (WHERE category_source = 'none')
            AS uncategorized_count
        ,string_agg(DISTINCT account_key, ', ' ORDER BY account_key)
            AS account_keys
        -- The most recent raw description, so the example is stable
        -- from one build to the next.
        ,arg_max(raw_description, txn_date) AS example_raw_description
    FROM transactions
    GROUP BY clean_description
)

,final AS (
    SELECT
        clean_description
        ,txn_count
        ,total_amount
        ,first_seen
        ,last_seen
        ,bank_guess
        ,uncategorized_count
        ,account_keys
        ,example_raw_description
    FROM by_description
)

SELECT
*
FROM final
