-- Every account's transactions in one shape. Add a new bank by adding
-- its staging model here.

{% set staging_models = [
    'stg_chase__checking_transactions',
    'stg_chase__card_transactions',
    'stg_amex__transactions',
] %}

{% for model in staging_models %}
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
    FROM {{ ref(model) }}
    {% if not loop.last %}UNION ALL{% endif %}
{% endfor %}
