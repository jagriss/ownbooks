-- Transfers with no opposite side in another account. This usually
-- means that account's statements haven't been exported yet, or the
-- export window cuts off one side, so the test warns and doesn't fail.

{{ config(severity='warn') }}

SELECT
txn_id
,account_key
,txn_date
,raw_description
,amount
FROM {{ ref('fct_transactions') }}
WHERE is_transfer AND transfer_matched_txn_id IS NULL
