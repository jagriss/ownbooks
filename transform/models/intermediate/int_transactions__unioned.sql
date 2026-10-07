-- Every account's transactions in one shape. Add a new bank with a CTE
-- selecting its staging model's columns in this same order (UNION ALL
-- matches columns by position, not name), then union it in below.

WITH chase_checking AS (

    SELECT
        txn_id,
        account_key,
        institution,
        txn_date,
        description,
        raw_description,
        amount,
        bank_type,
        bank_category,
        source_file,
        extracted_at
    FROM {{ ref('stg_chase__checking_transactions') }}

),

chase_card AS (

    SELECT
        txn_id,
        account_key,
        institution,
        txn_date,
        description,
        raw_description,
        amount,
        bank_type,
        bank_category,
        source_file,
        extracted_at
    FROM {{ ref('stg_chase__card_transactions') }}

),

amex AS (

    SELECT
        txn_id,
        account_key,
        institution,
        txn_date,
        description,
        raw_description,
        amount,
        bank_type,
        bank_category,
        source_file,
        extracted_at
    FROM {{ ref('stg_amex__transactions') }}

)

SELECT * FROM chase_checking
UNION ALL
SELECT * FROM chase_card
UNION ALL
SELECT * FROM amex
