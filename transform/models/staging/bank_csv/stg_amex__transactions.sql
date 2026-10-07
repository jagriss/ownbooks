-- Amex export (basic or extended). Amex signs amounts from the
-- issuer's side -- charges positive, payments and credits negative --
-- so the sign is flipped here to the outflow-negative convention.

WITH source AS (

    SELECT *
    FROM {{ source('raw_bank', 'transactions') }}
    WHERE layout = 'amex'

),

renamed AS (

    SELECT
        txn_hash AS txn_id,
        account_key,
        'amex' AS institution,
        cast(strptime(date, '%m/%d/%Y') AS date) AS txn_date,
        -- Amex pads the merchant name out with the city and state,
        -- separated by runs of spaces; keep only the merchant part.
        coalesce(
            nullif(regexp_extract(description, '^(.*?)\s{2,}', 1), ''),
            trim(description)
        ) AS description,
        description AS raw_description,
        -cast(amount AS decimal(12, 2)) AS amount,
        cast(NULL AS varchar) AS bank_type,
        nullif(category, '') AS bank_category,
        source_file,
        cast(extracted_at AS timestamp) AS extracted_at
    FROM source

)

SELECT *
FROM renamed
