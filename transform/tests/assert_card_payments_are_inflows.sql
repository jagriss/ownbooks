-- A payment to a credit card lands on the card as an inflow
-- (positive). A negative one means a staging model has that card's
-- sign convention backwards.

SELECT
txn_id
,account_key
,txn_date
,raw_description
,amount
FROM {{ ref('fct_transactions') }}
WHERE
    is_transfer
    AND account_type = 'credit'
    AND amount < 0
