-- Net spend per month and category. Transfers and income are excluded
-- (is_spend = false); refunds reduce their category's total.

WITH transactions AS (
    SELECT
        txn_month
        ,category_group
        ,category
        ,spend_amount
    FROM {{ ref('fct_transactions') }}
    WHERE is_spend
)

,by_month_category AS (
    SELECT
        strftime(txn_month, '%Y-%m') || '|' || category AS spend_key
        ,txn_month
        ,category_group
        ,category
        ,count(*) AS txn_count
        ,sum(spend_amount) AS spend
    FROM transactions
    GROUP BY txn_month, category_group, category
)

,final AS (
    SELECT
        spend_key
        ,txn_month
        ,category_group
        ,category
        ,txn_count
        ,spend
    FROM by_month_category
)

SELECT
*
FROM final
