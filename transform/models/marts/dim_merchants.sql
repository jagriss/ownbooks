-- One row per merchant, with lifetime spend and activity window.

SELECT
    merchant_name,
    -- A merchant can straddle categories (e.g. a refund rule); report
    -- the one most of its transactions fall under.
    mode(category) AS category,
    count(*) AS txn_count,
    sum(spend_amount) AS total_spend,
    min(txn_date) AS first_seen,
    max(txn_date) AS last_seen
FROM {{ ref('fct_transactions') }}
WHERE NOT is_transfer
GROUP BY merchant_name
