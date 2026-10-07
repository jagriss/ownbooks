-- Recurring charges: a merchant charging 3+ times at a monthly cadence
-- (every gap 25-35 days) for a near-constant amount (coefficient of
-- variation under 5%). The thresholds are strict so that regular but
-- variable spending, such as a grocery store visited monthly, is
-- excluded.

WITH charges AS (
    SELECT
        merchant_name
        ,category
        ,txn_date
        ,-amount AS charge_amount
        ,txn_date - lag(txn_date) OVER (
            PARTITION BY merchant_name ORDER BY txn_date
        ) AS gap_days
    FROM {{ ref('fct_transactions') }}
    WHERE is_spend AND amount < 0
)

,by_merchant AS (
    SELECT
        merchant_name
        ,mode(category) AS category
        ,count(*) AS charge_count
        ,avg(gap_days) AS avg_gap_days
        ,min(gap_days) AS min_gap_days
        ,max(gap_days) AS max_gap_days
        ,avg(charge_amount) AS avg_amount
        ,coalesce(stddev_samp(charge_amount), 0) AS stddev_amount
        ,min(txn_date) AS first_charged
        ,max(txn_date) AS last_charged
    FROM charges
    GROUP BY merchant_name
)

,recurring AS (
    SELECT
        merchant_name
        ,category
        ,charge_count
        ,round(avg_amount, 2) AS avg_amount
        ,round(avg_gap_days, 1) AS avg_gap_days
        ,first_charged
        ,last_charged
        ,cast(
            last_charged + to_days(cast(round(avg_gap_days) AS integer))
            AS date
        ) AS next_expected
        ,round(avg_amount * 12, 2) AS annualized_cost
    FROM by_merchant
    WHERE
        charge_count >= 3
        AND min_gap_days >= 25
        AND max_gap_days <= 35
        AND stddev_amount / avg_amount < 0.05
)

,final AS (
    SELECT
        merchant_name
        ,category
        ,charge_count
        ,avg_amount
        ,avg_gap_days
        ,first_charged
        ,last_charged
        ,next_expected
        ,annualized_cost
    FROM recurring
)

SELECT
*
FROM final
