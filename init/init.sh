#!/bin/bash
set -euo pipefail

cd /app

PROVISIONER_ENV=/app/stalwart/provisioner.env
BOOTSTRAP_ADMIN_ENV=/app/stalwart/bootstrap-admin.env

echo '=== mailstack: validate accounts ==='
tools/check-account-syntax.py

echo '=== mailstack: generate configuration ==='
tools/generate-config.py

echo '=== mailstack: initialize Stalwart if necessary ==='

#
# Normal/repeated startup: use the provisioner API key created during
# the first initialization.
#
if [ -f "$PROVISIONER_ENV" ]; then
    # shellcheck disable=SC1090
    . "$PROVISIONER_ENV"

    if [ -z "${STALWART_TOKEN:-}" ]; then
        echo 'ERROR: provisioner.env exists but contains no STALWART_TOKEN' >&2
        exit 1
    fi

    export STALWART_TOKEN
    unset STALWART_USER
    unset STALWART_PASSWORD

    echo 'Using persisted Stalwart provisioner API key'

else
    #
    # Recovery from an interrupted first boot:
    # Bootstrap may already have completed while API-key creation did not.
    #
    if [ -f "$BOOTSTRAP_ADMIN_ENV" ]; then
        # shellcheck disable=SC1090
        . "$BOOTSTRAP_ADMIN_ENV"

        if [ -z "${STALWART_USER:-}" ] || [ -z "${STALWART_PASSWORD:-}" ]; then
            echo 'ERROR: bootstrap-admin.env is incomplete' >&2
            exit 1
        fi

        export STALWART_USER
        export STALWART_PASSWORD
        unset STALWART_TOKEN || true

        echo 'Resuming interrupted Stalwart initialization'

    #
    # Virgin Stalwart: the temporary recovery credential supplied by
    # Compose can authenticate to the native Bootstrap endpoint.
    #
    elif bootstrap_check="$(stalwart-cli get Bootstrap 2>&1)"; then
        echo 'Stalwart is in bootstrap mode'

        bootstrap_output="$(
            stalwart-cli update Bootstrap \
                --field serverHostname=stalwart.mailstack.local \
                --field defaultDomain=mailstack.local \
                --field requestTlsCertificate=false \
                --field generateDkimKeys=false
        )"

        admin_user="$(
            printf '%s\n' "$bootstrap_output" |
            sed -n 's/^[[:space:]]*username: "\([^"]*\)".*/\1/p'
        )"

        admin_password="$(
            printf '%s\n' "$bootstrap_output" |
            sed -n 's/^[[:space:]]*secret: "\([^"]*\)".*/\1/p'
        )"

        unset bootstrap_output

        if [ -z "$admin_user" ] || [ -z "$admin_password" ]; then
            echo 'ERROR: Bootstrap completed but permanent admin credentials could not be parsed' >&2
            exit 1
        fi

        #
        # Save these immediately. If init dies while Stalwart is restarting,
        # the next invocation can continue instead of losing the generated
        # permanent credential.
        #
        umask 077
        printf 'STALWART_USER=%q\n' "$admin_user" > "$BOOTSTRAP_ADMIN_ENV"
        printf 'STALWART_PASSWORD=%q\n' "$admin_password" >> "$BOOTSTRAP_ADMIN_ENV"
        chmod 600 "$BOOTSTRAP_ADMIN_ENV"

        export STALWART_USER="$admin_user"
        export STALWART_PASSWORD="$admin_password"
        unset STALWART_TOKEN || true

        unset admin_user
        unset admin_password

        echo 'Stalwart bootstrap completed'

    else
        # Not in bootstrap mode, or Stalwart did not answer: say which.
        echo 'ERROR: no provisioner credentials (data/stalwart-provision/) and Stalwart is not' \
             'in bootstrap mode; its answer to the bootstrap check:' >&2
        printf '%s\n' "$bootstrap_check" | tail -3 >&2
        exit 1
    fi

    echo 'Waiting for normal Stalwart startup...'

    for attempt in $(seq 1 60); do
        if stalwart-cli query Domain >/dev/null 2>&1; then
            break
        fi

        if [ "$attempt" -eq 60 ]; then
            echo 'ERROR: Stalwart did not become available with permanent admin credentials' >&2
            exit 1
        fi

        sleep 1
    done

    echo 'Stalwart is running normally'
    echo 'Creating provisioner API key...'

    api_output="$(
        stalwart-cli create ApiKey \
            --field description='mailstack-provisioner' \
            --field 'permissions={"@type":"Inherit"}' \
            --field 'allowedIps={}'
    )"

    STALWART_TOKEN="$(
        printf '%s\n' "$api_output" |
        sed -n 's/^[[:space:]]*Secret:[[:space:]]*\(API_[^[:space:]]*\).*/\1/p'
    )"

    unset api_output

    if [ -z "$STALWART_TOKEN" ]; then
        echo 'ERROR: API key created but secret could not be parsed' >&2
        exit 1
    fi

    umask 077
    printf 'STALWART_TOKEN=%q\n' "$STALWART_TOKEN" > "$PROVISIONER_ENV"
    chmod 600 "$PROVISIONER_ENV"

    export STALWART_TOKEN
    unset STALWART_USER
    unset STALWART_PASSWORD

    rm -f "$BOOTSTRAP_ADMIN_ENV"

    echo 'Provisioner API key created and persisted'
fi

echo '=== mailstack: apply Stalwart configuration ==='
tools/stalwart-provision.py --apply

echo '=== mailstack: initialization complete ==='
