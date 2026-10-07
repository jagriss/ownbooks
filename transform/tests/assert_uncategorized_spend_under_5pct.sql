-- Warns while more than 5% of spend is uncategorized: time to work
-- through `pixi run todo` and add merchant rules.

{{ config(severity='warn') }}

WITH spend AS (

    SELECT
        sum(abs(spend_amount)) FILTER (WHERE category = 'Uncategorized')
            AS uncategorized,
        sum(abs(spend_amount)) AS total
    FROM {{ ref('fct_transactions') }}

)

SELECT
    uncategorized,
    total,
    round(100 * uncategorized / total, 1) AS uncategorized_pct
FROM spend
WHERE uncategorized / total > 0.05
