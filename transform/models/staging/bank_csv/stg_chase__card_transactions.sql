-- Chase credit card export. Purchases are negative and payments and
-- returns positive, which matches the outflow-negative convention.
-- Chase's own category is kept as bank_category for the
-- bank-category fallback in int_transactions__categorized.

WITH source AS (
    SELECT
        txn_hash
        ,account_key
        ,transaction_date
        ,description
        ,amount
        ,type
        ,category
        ,source_file
        ,extracted_at
    FROM {{ source('raw_bank', 'chase_card') }}
)

,renamed AS (
    SELECT
        txn_hash AS txn_id
        ,account_key
        ,'chase' AS institution
        ,cast(strptime(transaction_date, '%m/%d/%Y') AS date) AS txn_date
        ,trim(description) AS description
        ,description AS raw_description
        ,cast(amount AS decimal(12, 2)) AS amount
        ,type AS bank_type
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
