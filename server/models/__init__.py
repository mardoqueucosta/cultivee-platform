"""
Cultivee — Pacote de modelos (camada de dados).

Organizacao (v4.1.16 refactor):
  - db.py      -> conexao + init + migracoes
  - users.py   -> usuarios, auth, tokens, password reset, roles, prefs, profile
  - modules.py -> modulos do hardware, grupos, captura de camera
  - push.py    -> push subscriptions + alert_log
  - audit.py   -> audit_log de acoes admin

Este __init__ re-exporta todas as funcoes publicas pra manter compatibilidade
com imports existentes (ex: `import models; models.create_user(...)`).

NAO adicione logica nova aqui — adicione no modulo apropriado.
"""

# --- Database (connection + migrations) ---
from .db import (
    get_db,
    init_db,
    POLL_FAST,
    POLL_NORMAL,
    ACTIVITY_TIMEOUT,
)

# --- Users / auth / tokens / roles / profile ---
from .users import (
    # password
    hash_password,
    check_password,
    check_password_and_upgrade,
    needs_rehash,
    # CRUD
    create_user,
    get_user_by_email,
    get_user_by_id,
    update_user_password,
    # profile (v4.1.16)
    update_user_profile,
    PROFILE_EDITABLE_FIELDS,
    # LGPD + verificacao de email (v4.1.20)
    delete_user_cascade,
    export_user_data,
    generate_email_verification_token,
    verify_email_with_token,
    mark_terms_accepted,
    # 2FA TOTP (v4.1.22)
    set_totp_secret,
    enable_totp,
    disable_totp,
    # 2FA Email OTP (v4.1.29)
    create_email_2fa_code,
    verify_email_2fa_code,
    enable_email_2fa,
    disable_email_2fa,
    # Session management (v4.1.22)
    create_token_with_metadata,
    touch_token,
    list_user_sessions,
    revoke_token_by_id,
    revoke_all_other_tokens,
    # tokens
    create_token,
    create_impersonation_token,
    validate_token,
    validate_token_full,
    delete_token,
    # password reset
    create_password_reset_token,
    validate_password_reset_token,
    consume_password_reset_token,
    # admin / roles
    get_all_users,
    set_user_role,
    count_admins,
    get_admin_stats,
    # module prefs (UI state)
    get_user_module_prefs,
    save_user_module_prefs,
)

# --- Modules + groups + capture config ---
from .modules import (
    register_module,
    pair_module,
    unpair_module,
    get_user_modules,
    get_module_by_short_id,
    get_module_by_chip_id,
    get_all_modules_admin,
    mark_activity,
    get_poll_interval,
    update_ctrl_data,
    add_pending_command,
    get_pending_commands,
    create_group,
    get_user_groups,
    rename_group,
    delete_group,
    assign_module_to_group,
    remove_module_from_group,
    set_capture_config,
    get_capture_config,
    mark_capture,
    # Historico online/offline (v4.1.31)
    record_module_status,
    compute_module_status_lazy,
    get_module_uptime_summary,
    get_module_status_events,
    purge_old_status_events,
    MODULE_OFFLINE_THRESHOLD_SEC,
    MODULE_STATUS_RETENTION_DAYS,
)

# --- Push subscriptions + alert log ---
from .push import (
    save_push_subscription,
    delete_push_subscription,
    delete_push_subscription_by_endpoint,
    get_push_subscriptions,
    get_subscriptions_for_module,
    should_send_alert,
    log_alert,
)

# --- Audit log ---
from .audit import (
    log_admin_action,
    get_audit_log,
    get_audit_log_filtered,
)
