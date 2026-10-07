-- Chase checking export. Amounts are already signed from the
-- account's point of view (debits negative), which is the convention
-- every staging model normalizes to.

WITH source AS (

    SELECT *
    FROM {{ source('raw_bank', 'transactions') }}
    WHERE layout = 'chase_checking'

),

renamed AS (

    SELECT
        txn_hash AS txn_id,
        account_key,
        'chase' AS institution,
        cast(strptime(posting_date, '%m/%d/%Y') AS date) AS txn_date,
        trim(description) AS description,
        description AS raw_description,
        cast(amount AS decimal(12, 2)) AS amount,
        type AS bank_type,
        cast(NULL AS varchar) AS bank_category,
        source_file,
        cast(extracted_at AS timestamp) AS extracted_at
    FROM source

)

SELECT *
FROM renamed
