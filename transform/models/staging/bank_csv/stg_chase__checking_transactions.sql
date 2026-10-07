-- Chase checking export. Amounts are signed from the account holder's
-- side (debits negative), the convention every staging model outputs.

WITH source AS (
    SELECT
        txn_hash
        ,account_key
        ,posting_date
        ,description
        ,amount
        ,type
        ,source_file
        ,extracted_at
    FROM {{ source('raw_bank', 'chase_checking') }}
)

,renamed AS (
    SELECT
        txn_hash AS txn_id
        ,account_key
        ,'chase' AS institution
        ,cast(strptime(posting_date, '%m/%d/%Y') AS date) AS txn_date
        ,trim(description) AS description
        ,description AS raw_description
        ,cast(amount AS decimal(12, 2)) AS amount
        ,type AS bank_type
        ,cast(NULL AS varchar) AS bank_category
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
