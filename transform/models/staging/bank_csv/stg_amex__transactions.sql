-- Amex export (basic or extended). Amex signs amounts from the
-- issuer's side (charges positive, payments and credits negative), so
-- the sign is flipped to the outflow-negative convention.

WITH source AS (
    SELECT
        txn_hash
        ,account_key
        ,date
        ,description
        ,amount
        ,category
        ,source_file
        ,extracted_at
    FROM {{ source('raw_bank', 'amex') }}
)

,renamed AS (
    SELECT
        txn_hash AS txn_id
        ,account_key
        ,'amex' AS institution
        ,cast(strptime(date, '%m/%d/%Y') AS date) AS txn_date
        -- Amex pads the merchant name with the city and state,
        -- separated by runs of spaces; only the merchant part is kept.
        ,coalesce(
            nullif(regexp_extract(description, '^(.*?)\s{2,}', 1), '')
            ,trim(description)
        ) AS description
        ,description AS raw_description
        ,-cast(amount AS decimal(12, 2)) AS amount
        ,cast(NULL AS varchar) AS bank_type
        ,nullif(category, '') AS bank_category
        ,source_file
        ,cast(extracted_at AS timestamp) AS extracted_at
    FROM source
)

,final AS (
    SELECT
        txn_id
        ,account_key
        ,institution
        ,txn_date
        ,description
        ,raw_description
        ,amount
        ,bank_type
        ,bank_category
        ,source_file
        ,extracted_at
    FROM renamed
)

SELECT
*
FROM final
