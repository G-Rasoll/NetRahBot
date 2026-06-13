CREATE DATABASE NetRah;
GO

USE NetRah;
GO


CREATE TABLE invoice_statuses
(
    id INT PRIMARY KEY,
    status_name NVARCHAR(50) NOT NULL UNIQUE
);
GO

CREATE TABLE users
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    username NVARCHAR(255) NULL,
    first_name NVARCHAR(255) NOT NULL,
    balance DECIMAL(20,9) NOT NULL 
        CONSTRAINT DF_Users_Balance DEFAULT (0),
    has_used_test_package BIT NOT NULL 
        CONSTRAINT DF_Users_HasUsedTestPackage DEFAULT (0),
    is_banned BIT NOT NULL 
        CONSTRAINT DF_Users_IsBanned DEFAULT (0),
    referral_token NVARCHAR(64) NULL, -- توکن رندوم امن برای لینک دعوت
    created_at DATETIME2 NOT NULL 
        CONSTRAINT DF_Users_CreatedAt DEFAULT (GETDATE())
);
GO

CREATE TABLE packages
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    title NVARCHAR(100) NOT NULL,
    volume_mb INT NOT NULL,
    price_rial BIGINT NOT NULL,
    is_test_package BIT NOT NULL 
        CONSTRAINT DF_Packages_IsTestPackage DEFAULT (0),
    is_active BIT NOT NULL 
        CONSTRAINT DF_Packages_IsActive DEFAULT (1),
    is_gift_package BIT NOT NULL 
        CONSTRAINT DF_Packages_IsGiftPackage DEFAULT (0), 
    created_at DATETIME2 NOT NULL 
        CONSTRAINT DF_Packages_CreatedAt DEFAULT (GETDATE())
);
GO

-- ==========================================
-- ۲. ساخت جداول وابسته (دارای کلید خارجی)
-- ==========================================

CREATE TABLE subscription_inventory
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    package_id INT NOT NULL,
    subscription_link NVARCHAR(MAX) NOT NULL,
    is_assigned BIT NOT NULL 
        CONSTRAINT DF_SubInventory_IsAssigned DEFAULT (0),
    created_at DATETIME2 NOT NULL 
        CONSTRAINT DF_SubInventory_CreatedAt DEFAULT (GETDATE()),

    CONSTRAINT FK_SubInventory_Packages
        FOREIGN KEY (package_id) REFERENCES packages(id)
);
GO

CREATE TABLE invoices
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    user_id INT NOT NULL,
    package_id INT NOT NULL,
    memo NVARCHAR(64) NOT NULL UNIQUE,
    status_id INT NOT NULL 
        CONSTRAINT DF_Invoices_Status DEFAULT (1),
    package_title_snapshot NVARCHAR(100) NOT NULL,
    package_price_snapshot_rial BIGINT NOT NULL,
    package_volume_snapshot_mb INT NOT NULL,
    payment_currency_code NVARCHAR(20) NOT NULL,
    expected_payment_amount DECIMAL(20,9) NOT NULL,
    amount_received DECIMAL(20,9) NOT NULL 
        CONSTRAINT DF_Invoices_AmountReceived DEFAULT (0),
    tx_hash NVARCHAR(100) NULL,
    expires_at DATETIME2 NOT NULL,
    created_at DATETIME2 NOT NULL 
        CONSTRAINT DF_Invoices_CreatedAt DEFAULT (GETDATE()),

    CONSTRAINT FK_Invoices_Users
        FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT FK_Invoices_Packages
        FOREIGN KEY (package_id) REFERENCES packages(id),
    CONSTRAINT FK_Invoices_Statuses
        FOREIGN KEY (status_id) REFERENCES invoice_statuses(id)
);
GO

CREATE TABLE user_subscriptions
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    user_id INT NOT NULL,
    inventory_id INT NOT NULL UNIQUE,
    invoice_id INT NULL,
    assigned_at DATETIME2 NOT NULL 
        CONSTRAINT DF_UserSubscriptions_AssignedAt DEFAULT (GETDATE()),

    CONSTRAINT FK_UserSubscriptions_Users
        FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT FK_UserSubscriptions_Inventory
        FOREIGN KEY (inventory_id) REFERENCES subscription_inventory(id),
    CONSTRAINT FK_UserSubscriptions_Invoices
        FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);
GO

CREATE TABLE referral_settings
(
    id INT PRIMARY KEY CONSTRAINT DF_ReferralSettings_Id DEFAULT (1),
    required_invites INT NOT NULL CONSTRAINT DF_ReferralSettings_RequiredInvites DEFAULT (5),
    gift_package_id INT NULL, 
    CONSTRAINT CK_ReferralSettings_SingleRow CHECK (id = 1) 
);
GO

CREATE TABLE user_referral_stats
(
    user_id INT PRIMARY KEY,
    current_points INT NOT NULL CONSTRAINT DF_UserReferralStats_CurrentPoints DEFAULT (0),
    total_invites INT NOT NULL CONSTRAINT DF_UserReferralStats_TotalInvites DEFAULT (0),
    CONSTRAINT FK_UserReferralStats_Users FOREIGN KEY (user_id) REFERENCES users(id)
);
GO

CREATE TABLE referrals
(
    id INT IDENTITY(1,1) PRIMARY KEY,
    inviter_id INT NOT NULL,
    referee_telegram_id BIGINT NOT NULL CONSTRAINT UQ_Referrals_RefereeTelegramId UNIQUE,
    status NVARCHAR(20) NOT NULL CONSTRAINT DF_Referrals_Status DEFAULT ('PENDING'),
    created_at DATETIME2 NOT NULL CONSTRAINT DF_Referrals_CreatedAt DEFAULT (GETDATE()),
    completed_at DATETIME2 NULL,
    CONSTRAINT FK_Referrals_Inviter FOREIGN KEY (inviter_id) REFERENCES users(id)
);
GO


-- ==========================================
-- ۳. ساخت شاخص‌ها (Indexes) بهینه‌سازی و امنیت
-- ==========================================
CREATE UNIQUE INDEX UX_Invoices_TxHash
ON invoices(tx_hash)
WHERE tx_hash IS NOT NULL;
GO

CREATE UNIQUE INDEX UX_Users_ReferralToken 
ON users(referral_token) 
WHERE referral_token IS NOT NULL;
GO

CREATE INDEX IX_Referrals_Status_Referee 
ON referrals(referee_telegram_id, status);
GO


INSERT INTO invoice_statuses (id, status_name)
VALUES 
(1, 'PENDING'),
(2, 'PAID'),
(3, 'COMPLETED'),
(4, 'EXPIRED'),
(5, 'FAILED');
GO

INSERT INTO packages (title, volume_mb, price_rial, is_test_package, is_active, is_gift_package)
VALUES (N'🎁 هدیه ۱ گیگابایتی دعوت', 1024, 0, 0, 1, 1);
GO

DECLARE @GiftPkgId INT;
SELECT @GiftPkgId = id FROM packages WHERE is_gift_package = 1;

INSERT INTO referral_settings (id, required_invites, gift_package_id)
VALUES (1, 5, @GiftPkgId);
GO