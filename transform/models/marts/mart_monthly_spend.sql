-- Net spend per month and category. Transfers and income are excluded
-- (is_spend = false); refunds reduce their category's total.

SELECT
    txn_month,
    category_group,
    category,
    count(*) AS txn_count,
    sum(spend_amount) AS spend
FROM {{ ref('fct_transactions') }}
WHERE is_spend
GROUP BY txn_month, category_group, category
