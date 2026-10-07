-- One row per transaction across all accounts, categorized, with
-- transfer pairing resolved. The table every other mart reads.

WITH categorized AS (

    SELECT *
    FROM {{ ref('int_transactions__categorized') }}

),

transfers AS (

    SELECT *
    FROM {{ ref('int_transactions__transfers') }}

),

accounts AS (

    SELECT *
    FROM {{ ref('accounts') }}

),

categories AS (

    SELECT *
    FROM {{ ref('categories') }}

)

SELECT
    categorized.txn_id,
    categorized.txn_date,
    cast(date_trunc('month', categorized.txn_date) AS date) AS txn_month,
    categorized.account_key,
    accounts.account_name,
    accounts.account_type,
    categorized.institution,
    categorized.raw_description,
    categorized.clean_description,
    categorized.merchant_name,
    categorized.category,
    categorized.category_source,
    categories.category_group,
    categories.is_essential,
    categories.is_spend,
    categorized.category = 'Transfer' AS is_transfer,
    transfers.matched_txn_id AS transfer_matched_txn_id,
    categorized.amount,
    -- Positive = money spent; refunds in a spend category net it down.
    CASE WHEN categories.is_spend THEN -categorized.amount END
        AS spend_amount,
    categorized.matched_pattern,
    categorized.bank_type,
    categorized.bank_category,
    categorized.source_file,
    categorized.extracted_at
FROM categorized
LEFT JOIN accounts
    ON categorized.account_key = accounts.account_key
LEFT JOIN categories
    ON categorized.category = categories.category
LEFT JOIN transfers
    ON categorized.txn_id = transfers.txn_id
