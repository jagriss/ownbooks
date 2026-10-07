-- Chase credit card export. Purchases are negative and payments /
-- returns positive, matching the outflow-negative convention as-is.
-- Chase's own category is kept as bank_category for reference only.

WITH source AS (

    SELECT *
    FROM {{ source('raw_bank', 'transactions') }}
    WHERE layout = 'chase_card'

),

renamed AS (

    SELECT
        txn_hash AS txn_id,
        account_key,
        'chase' AS institution,
        cast(strptime(transaction_date, '%m/%d/%Y') AS date) AS txn_date,
        trim(description) AS description,
        description AS raw_description,
        cast(amount AS decimal(12, 2)) AS amount,
        type AS bank_type,
        nullif(category, '') AS bank_category,
        source_file,
        cast(extracted_at AS timestamp) AS extracted_at
    FROM source

)

SELECT *
FROM renamed
