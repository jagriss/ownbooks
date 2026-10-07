-- Warns while more than 5% of spend is uncategorized; the Categorize
-- page in the app lists what needs a merchant rule.

{{ config(severity='warn') }}

WITH spend AS (
    SELECT
        sum(abs(spend_amount)) FILTER (WHERE category = 'Uncategorized')
            AS uncategorized
        ,sum(abs(spend_amount)) AS total
    FROM {{ ref('fct_transactions') }}
)

,over_threshold AS (
    SELECT
        uncategorized
        ,total
        ,round(100 * uncategorized / total, 1) AS uncategorized_pct
    FROM spend
    WHERE uncategorized / total > 0.05
)

,final AS (
    SELECT
        uncategorized
        ,total
        ,uncategorized_pct
    FROM over_threshold
)

SELECT
*
FROM final
