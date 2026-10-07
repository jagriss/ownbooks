-- One row per merchant, with lifetime spend and activity window.
-- Transfers are excluded.

WITH transactions AS (
    SELECT
        merchant_name
        ,category
        ,spend_amount
        ,txn_date
    FROM {{ ref('fct_transactions') }}
    WHERE NOT is_transfer
)

,by_merchant AS (
    SELECT
        merchant_name
        -- A merchant can span categories (e.g. via a refund rule); the
        -- category most of its transactions fall under is reported.
        ,mode(category) AS category
        ,count(*) AS txn_count
        ,sum(spend_amount) AS total_spend
        ,min(txn_date) AS first_seen
        ,max(txn_date) AS last_seen
    FROM transactions
    GROUP BY merchant_name
)

,final AS (
    SELECT
        merchant_name
        ,category
        ,txn_count
        ,total_spend
        ,first_seen
        ,last_seen
    FROM by_merchant
)

SELECT
*
FROM final
