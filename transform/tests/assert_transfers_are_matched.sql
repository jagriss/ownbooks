-- Transfers with no opposite side in another account. Usually means
-- that account's statements haven't been exported yet (or the export
-- window cuts off one side); warn rather than fail.

{{ config(severity='warn') }}

SELECT
    txn_id,
    account_key,
    txn_date,
    raw_description,
    amount
FROM {{ ref('fct_transactions') }}
WHERE is_transfer AND transfer_matched_txn_id IS NULL
