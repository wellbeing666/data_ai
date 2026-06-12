CREATE DATABASE IF NOT EXISTS ai_data_workbench CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ai_data_workbench;

CREATE TABLE IF NOT EXISTS users (
    id CHAR(32) PRIMARY KEY,
    login_account VARCHAR(80) NOT NULL UNIQUE,
    username VARCHAR(50) NOT NULL,
    role VARCHAR(20) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,
    register_reason VARCHAR(500) DEFAULT '',
    audit_reason VARCHAR(500) DEFAULT '',
    approved_by CHAR(32) NULL,
    approved_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    last_login_at DATETIME(6) NULL,
    CONSTRAINT fk_users_approved_by FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_users_status (status),
    INDEX idx_users_role (role),
    INDEX idx_users_account (login_account)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id CHAR(32) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    expires_at DATETIME(6) NOT NULL,
    revoked_at DATETIME(6) NULL,
    user_agent VARCHAR(300) DEFAULT '',
    CONSTRAINT fk_auth_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_sessions_user (user_id),
    INDEX idx_sessions_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS analysis_conversations (
    job_id CHAR(32) PRIMARY KEY,
    dataset_id VARCHAR(80) NULL,
    owner_user_id CHAR(32) NULL,
    user_goal TEXT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'pending',
    current_stage VARCHAR(80) NULL,
    workflow_type VARCHAR(80) NULL,
    task_type VARCHAR(80) NULL,
    asset_type VARCHAR(40) NULL,
    dataset_filename VARCHAR(255) NULL,
    file_type VARCHAR(40) NULL,
    chart_count INT NOT NULL DEFAULT 0,
    job_dir VARCHAR(1024) NOT NULL,
    status_payload JSON NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    deleted_at DATETIME(6) NULL,
    CONSTRAINT fk_analysis_conversations_owner FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_conversations_owner_updated (owner_user_id, updated_at),
    INDEX idx_conversations_status (status),
    INDEX idx_conversations_dataset (dataset_id),
    FULLTEXT INDEX ft_conversations_goal_dataset (user_goal, dataset_filename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
