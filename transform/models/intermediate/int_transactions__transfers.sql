-- Pairs the two sides of each money movement between your own
-- accounts, e.g. the checking debit and the card credit of a card
-- payment, so neither side counts as spending or income. A pair is
-- opposite amounts, in different accounts, posted within 5 days; the
-- closest-dated candidate wins and each transaction pairs at most once.
-- One row per side of each pair.

WITH transfers AS (
    SELECT
        txn_id
        ,account_key
        ,txn_date
        ,amount
    FROM {{ ref('int_transactions__categorized') }}
    WHERE category = 'Transfer'
)

,candidates AS (
    SELECT
        outflow.txn_id AS outflow_txn_id
        ,inflow.txn_id AS inflow_txn_id
        ,row_number() OVER (
            PARTITION BY outflow.txn_id
            ORDER BY abs(inflow.txn_date - outflow.txn_date), inflow.txn_id
        ) AS outflow_rank
        ,row_number() OVER (
            PARTITION BY inflow.txn_id
            ORDER BY abs(inflow.txn_date - outflow.txn_date), outflow.txn_id
        ) AS inflow_rank
    FROM transfers AS outflow
    INNER JOIN transfers AS inflow
        ON
            outflow.amount = -inflow.amount
            AND outflow.account_key != inflow.account_key
            AND abs(inflow.txn_date - outflow.txn_date) <= 5
    WHERE outflow.amount < 0
)

,pairs AS (
    SELECT
        outflow_txn_id
        ,inflow_txn_id
    FROM candidates
    WHERE outflow_rank = 1 AND inflow_rank = 1
)

,both_sides AS (
    SELECT
        outflow_txn_id AS txn_id
        ,inflow_txn_id AS matched_txn_id
    FROM pairs
    UNION ALL
    SELECT
        inflow_txn_id AS txn_id
        ,outflow_txn_id AS matched_txn_id
    FROM pairs
)

,final AS (
    SELECT
        txn_id
        ,matched_txn_id
    FROM both_sides
)

SELECT
*
FROM final
