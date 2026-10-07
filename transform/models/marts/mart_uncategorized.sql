-- The categorization to-do list: uncategorized descriptions, biggest
-- money first. Each row needs a pattern in seeds/merchant_rules.csv.

SELECT
    clean_description,
    count(*) AS txn_count,
    sum(amount) AS total_amount,
    min(txn_date) AS first_seen,
    max(txn_date) AS last_seen,
    string_agg(DISTINCT account_key, ', ') AS account_keys,
    any_value(raw_description) AS example_raw_description
FROM {{ ref('fct_transactions') }}
WHERE category = 'Uncategorized'
GROUP BY clean_description
ORDER BY abs(sum(amount)) DESC
