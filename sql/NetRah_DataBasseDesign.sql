-- ==========================================
-- ایجاد دیتابیس NetRah
-- ==========================================
USE [master]
GO

CREATE DATABASE [NetRah]
 CONTAINMENT = NONE
 ON PRIMARY 
( NAME = N'NetRah', FILENAME = N'C:\Program Files\Microsoft SQL Server\MSSQL16.SQL22\MSSQL\DATA\NetRah.mdf' , SIZE = 8192KB , MAXSIZE = UNLIMITED, FILEGROWTH = 65536KB )
 LOG ON 
( NAME = N'NetRah_log', FILENAME = N'C:\Program Files\Microsoft SQL Server\MSSQL16.SQL22\MSSQL\DATA\NetRah_log.ldf' , SIZE = 73728KB , MAXSIZE = 2048GB , FILEGROWTH = 65536KB )
 WITH CATALOG_COLLATION = DATABASE_DEFAULT, LEDGER = OFF
GO

-- ==========================================
-- تنظیمات سطح دیتابیس
-- ==========================================
ALTER DATABASE [NetRah] SET COMPATIBILITY_LEVEL = 160
GO

IF (1 = FULLTEXTSERVICEPROPERTY('IsFullTextInstalled'))
BEGIN
    EXEC [NetRah].[dbo].[sp_fulltext_database] @action = 'enable'
END
GO

ALTER DATABASE [NetRah] SET 
    ANSI_NULL_DEFAULT OFF,
    ANSI_NULLS OFF,
    ANSI_PADDING OFF,
    ANSI_WARNINGS OFF,
    ARITHABORT OFF,
    AUTO_CLOSE OFF,
    AUTO_SHRINK OFF,
    AUTO_UPDATE_STATISTICS ON,
    CURSOR_CLOSE_ON_COMMIT OFF,
    CURSOR_DEFAULT GLOBAL,
    CONCAT_NULL_YIELDS_NULL OFF,
    NUMERIC_ROUNDABORT OFF,
    QUOTED_IDENTIFIER OFF,
    RECURSIVE_TRIGGERS OFF,
    ENABLE_BROKER,
    AUTO_UPDATE_STATISTICS_ASYNC OFF,
    DATE_CORRELATION_OPTIMIZATION OFF,
    TRUSTWORTHY OFF,
    ALLOW_SNAPSHOT_ISOLATION OFF,
    PARAMETERIZATION SIMPLE,
    READ_COMMITTED_SNAPSHOT OFF,
    HONOR_BROKER_PRIORITY OFF,
    RECOVERY FULL,
    MULTI_USER,
    PAGE_VERIFY CHECKSUM,
    DB_CHAINING OFF,
    FILESTREAM(NON_TRANSACTED_ACCESS = OFF),
    TARGET_RECOVERY_TIME = 60 SECONDS,
    DELAYED_DURABILITY = DISABLED,
    ACCELERATED_DATABASE_RECOVERY = OFF
GO

EXEC sys.sp_db_vardecimal_storage_format N'NetRah', N'ON'
GO

ALTER DATABASE [NetRah] SET QUERY_STORE = ON
GO

ALTER DATABASE [NetRah] SET QUERY_STORE (
    OPERATION_MODE = READ_WRITE,
    CLEANUP_POLICY = (STALE_QUERY_THRESHOLD_DAYS = 30),
    DATA_FLUSH_INTERVAL_SECONDS = 900,
    INTERVAL_LENGTH_MINUTES = 60,
    MAX_STORAGE_SIZE_MB = 1000,
    QUERY_CAPTURE_MODE = AUTO,
    SIZE_BASED_CLEANUP_MODE = AUTO,
    MAX_PLANS_PER_QUERY = 200,
    WAIT_STATS_CAPTURE_MODE = ON
)
GO

-- ==========================================
-- سوئیچ به دیتابیس جدید
-- ==========================================
USE [NetRah]
GO

-- ==========================================
-- ایجاد جدول users
-- ==========================================
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[users](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [telegram_id] [bigint] NOT NULL,
    [username] [nvarchar](255) NULL,
    [first_name] [nvarchar](255) NOT NULL,
    [balance] [decimal](20, 9) NOT NULL,
    [has_used_test_package] [bit] NOT NULL,
    [is_banned] [bit] NOT NULL,
    [created_at] [datetime2](7) NOT NULL,
    [referral_token] [nvarchar](64) NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
    UNIQUE NONCLUSTERED ([telegram_id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

CREATE UNIQUE NONCLUSTERED INDEX [UX_Users_ReferralToken] ON [dbo].[users](
    [referral_token] ASC
)
WHERE ([referral_token] IS NOT NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO

ALTER TABLE [dbo].[users] ADD CONSTRAINT [DF_Users_Balance] DEFAULT ((0)) FOR [balance]
GO
ALTER TABLE [dbo].[users] ADD CONSTRAINT [DF_Users_HasUsedTestPackage] DEFAULT ((0)) FOR [has_used_test_package]
GO
ALTER TABLE [dbo].[users] ADD CONSTRAINT [DF_Users_IsBanned] DEFAULT ((0)) FOR [is_banned]
GO
ALTER TABLE [dbo].[users] ADD CONSTRAINT [DF_Users_CreatedAt] DEFAULT (getdate()) FOR [created_at]
GO

-- ==========================================
-- ایجاد جدول admins
-- ==========================================
CREATE TABLE [dbo].[admins](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [user_id] [int] NOT NULL,
    [brand_name] [nvarchar](100) NOT NULL,
    [added_at] [datetime2](7) NOT NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
    UNIQUE NONCLUSTERED ([user_id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[admins] ADD CONSTRAINT [DF_Admins_Brand] DEFAULT ('NetRah') FOR [brand_name]
GO
ALTER TABLE [dbo].[admins] ADD CONSTRAINT [DF_Admins_AddedAt] DEFAULT (getdate()) FOR [added_at]
GO

ALTER TABLE [dbo].[admins] WITH CHECK ADD CONSTRAINT [FK_Admins_Users] FOREIGN KEY([user_id]) REFERENCES [dbo].[users] ([id])
GO
ALTER TABLE [dbo].[admins] CHECK CONSTRAINT [FK_Admins_Users]
GO

-- ==========================================
-- ایجاد جدول packages
-- ==========================================
CREATE TABLE [dbo].[packages](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [title] [nvarchar](100) NOT NULL,
    [volume_mb] [int] NOT NULL,
    [price_rial] [bigint] NOT NULL,
    [is_test_package] [bit] NOT NULL,
    [is_active] [bit] NOT NULL,
    [created_at] [datetime2](7) NOT NULL,
    [is_gift_package] [bit] NOT NULL,
    [volume_gb] [decimal](10, 4) NOT NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[packages] ADD CONSTRAINT [DF_Packages_IsTestPackage] DEFAULT ((0)) FOR [is_test_package]
GO
ALTER TABLE [dbo].[packages] ADD CONSTRAINT [DF_Packages_IsActive] DEFAULT ((1)) FOR [is_active]
GO
ALTER TABLE [dbo].[packages] ADD CONSTRAINT [DF_Packages_CreatedAt] DEFAULT (getdate()) FOR [created_at]
GO
ALTER TABLE [dbo].[packages] ADD CONSTRAINT [DF_Packages_IsGiftPackage] DEFAULT ((0)) FOR [is_gift_package]
GO
ALTER TABLE [dbo].[packages] ADD CONSTRAINT [DF_Packages_VolumeGB] DEFAULT ((0)) FOR [volume_gb]
GO

-- ==========================================
-- ایجاد جدول invoice_statuses
-- ==========================================
CREATE TABLE [dbo].[invoice_statuses](
    [id] [int] NOT NULL,
    [status_name] [nvarchar](50) NOT NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
    UNIQUE NONCLUSTERED ([status_name] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

-- ==========================================
-- ایجاد جدول discount_codes
-- ==========================================
CREATE TABLE [dbo].[discount_codes](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [code] [nvarchar](50) NOT NULL,
    [discount_type] [nvarchar](20) NOT NULL,
    [discount_value] [decimal](20, 9) NOT NULL,
    [max_discount_amount] [bigint] NULL,
    [min_order_amount] [bigint] NULL,
    [total_usage_limit] [int] NULL,
    [used_count] [int] NOT NULL,
    [user_usage_limit] [int] NOT NULL,
    [bound_user_id] [int] NULL,
    [bound_package_id] [int] NULL,
    [valid_from] [datetime2](7) NOT NULL,
    [expires_at] [datetime2](7) NULL,
    [status] [nvarchar](20) NOT NULL,
    [created_at] [datetime2](7) NOT NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
    UNIQUE NONCLUSTERED ([code] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_DiscountCodes_Code] ON [dbo].[discount_codes](
    [code] ASC
) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO

ALTER TABLE [dbo].[discount_codes] ADD DEFAULT ((0)) FOR [used_count]
GO
ALTER TABLE [dbo].[discount_codes] ADD DEFAULT ((1)) FOR [user_usage_limit]
GO
ALTER TABLE [dbo].[discount_codes] ADD DEFAULT (getdate()) FOR [valid_from]
GO
ALTER TABLE [dbo].[discount_codes] ADD DEFAULT ('ACTIVE') FOR [status]
GO
ALTER TABLE [dbo].[discount_codes] ADD DEFAULT (getdate()) FOR [created_at]
GO

ALTER TABLE [dbo].[discount_codes] WITH CHECK ADD FOREIGN KEY([bound_user_id]) REFERENCES [dbo].[users] ([id])
GO
ALTER TABLE [dbo].[discount_codes] WITH CHECK ADD FOREIGN KEY([bound_package_id]) REFERENCES [dbo].[packages] ([id])
GO
ALTER TABLE [dbo].[discount_codes] WITH CHECK ADD CHECK (([discount_type]='FIXED' OR [discount_type]='PERCENT'))
GO
ALTER TABLE [dbo].[discount_codes] WITH CHECK ADD CHECK (([status]='INACTIVE' OR [status]='ACTIVE'))
GO

-- ==========================================
-- ایجاد جدول invoices
-- ==========================================
CREATE TABLE [dbo].[invoices](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [user_id] [int] NOT NULL,
    [package_id] [int] NOT NULL,
    [status_id] [int] NOT NULL,
    [package_title_snapshot] [nvarchar](100) NOT NULL,
    [package_price_snapshot_rial] [bigint] NOT NULL,
    [package_volume_snapshot_mb] [int] NOT NULL,
    [payment_currency_code] [nvarchar](20) NOT NULL,
    [expected_payment_amount] [decimal](20, 9) NOT NULL,
    [amount_received] [decimal](20, 9) NOT NULL,
    [tx_hash] [nvarchar](100) NULL,
    [expires_at] [datetime2](7) NOT NULL,
    [created_at] [datetime2](7) NOT NULL,
    [custom_config_name] [nvarchar](100) NULL,
    [chat_id] [bigint] NULL,
    [message_id] [int] NULL,
    [discount_id] [int] NULL,
    [discount_amount_rial] [bigint] NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

CREATE UNIQUE NONCLUSTERED INDEX [UX_Invoices_TxHash] ON [dbo].[invoices](
    [tx_hash] ASC
)
WHERE ([tx_hash] IS NOT NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO

ALTER TABLE [dbo].[invoices] ADD CONSTRAINT [DF_Invoices_Status] DEFAULT ((1)) FOR [status_id]
GO
ALTER TABLE [dbo].[invoices] ADD CONSTRAINT [DF_Invoices_AmountReceived] DEFAULT ((0)) FOR [amount_received]
GO
ALTER TABLE [dbo].[invoices] ADD CONSTRAINT [DF_Invoices_CreatedAt] DEFAULT (getdate()) FOR [created_at]
GO
ALTER TABLE [dbo].[invoices] ADD DEFAULT ((0)) FOR [discount_amount_rial]
GO

ALTER TABLE [dbo].[invoices] WITH CHECK ADD FOREIGN KEY([discount_id]) REFERENCES [dbo].[discount_codes] ([id])
GO
ALTER TABLE [dbo].[invoices] WITH CHECK ADD CONSTRAINT [FK_Invoices_Packages] FOREIGN KEY([package_id]) REFERENCES [dbo].[packages] ([id])
GO
ALTER TABLE [dbo].[invoices] CHECK CONSTRAINT [FK_Invoices_Packages]
GO
ALTER TABLE [dbo].[invoices] WITH CHECK ADD CONSTRAINT [FK_Invoices_Statuses] FOREIGN KEY([status_id]) REFERENCES [dbo].[invoice_statuses] ([id])
GO
ALTER TABLE [dbo].[invoices] CHECK CONSTRAINT [FK_Invoices_Statuses]
GO
ALTER TABLE [dbo].[invoices] WITH CHECK ADD CONSTRAINT [FK_Invoices_Users] FOREIGN KEY([user_id]) REFERENCES [dbo].[users] ([id])
GO
ALTER TABLE [dbo].[invoices] CHECK CONSTRAINT [FK_Invoices_Users]
GO

-- ==========================================
-- ایجاد جدول subscription_inventory
-- ==========================================
CREATE TABLE [dbo].[subscription_inventory](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [package_id] [int] NOT NULL,
    [subscription_link] [nvarchar](max) NOT NULL,
    [is_assigned] [bit] NOT NULL,
    [created_at] [datetime2](7) NOT NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO

ALTER TABLE [dbo].[subscription_inventory] ADD CONSTRAINT [DF_SubInventory_IsAssigned] DEFAULT ((0)) FOR [is_assigned]
GO
ALTER TABLE [dbo].[subscription_inventory] ADD CONSTRAINT [DF_SubInventory_CreatedAt] DEFAULT (getdate()) FOR [created_at]
GO

ALTER TABLE [dbo].[subscription_inventory] WITH CHECK ADD CONSTRAINT [FK_SubInventory_Packages] FOREIGN KEY([package_id]) REFERENCES [dbo].[packages] ([id])
GO
ALTER TABLE [dbo].[subscription_inventory] CHECK CONSTRAINT [FK_SubInventory_Packages]
GO

-- ==========================================
-- ایجاد جدول user_subscriptions
-- ==========================================
CREATE TABLE [dbo].[user_subscriptions](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [user_id] [int] NOT NULL,
    [inventory_id] [int] NOT NULL,
    [invoice_id] [int] NULL,
    [assigned_at] [datetime2](7) NOT NULL,
    [config_name] [nvarchar](100) NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
    UNIQUE NONCLUSTERED ([inventory_id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[user_subscriptions] ADD CONSTRAINT [DF_UserSubscriptions_AssignedAt] DEFAULT (getdate()) FOR [assigned_at]
GO

ALTER TABLE [dbo].[user_subscriptions] WITH CHECK ADD CONSTRAINT [FK_UserSubscriptions_Inventory] FOREIGN KEY([inventory_id]) REFERENCES [dbo].[subscription_inventory] ([id])
GO
ALTER TABLE [dbo].[user_subscriptions] CHECK CONSTRAINT [FK_UserSubscriptions_Inventory]
GO
ALTER TABLE [dbo].[user_subscriptions] WITH CHECK ADD CONSTRAINT [FK_UserSubscriptions_Invoices] FOREIGN KEY([invoice_id]) REFERENCES [dbo].[invoices] ([id])
GO
ALTER TABLE [dbo].[user_subscriptions] CHECK CONSTRAINT [FK_UserSubscriptions_Invoices]
GO
ALTER TABLE [dbo].[user_subscriptions] WITH CHECK ADD CONSTRAINT [FK_UserSubscriptions_Users] FOREIGN KEY([user_id]) REFERENCES [dbo].[users] ([id])
GO
ALTER TABLE [dbo].[user_subscriptions] CHECK CONSTRAINT [FK_UserSubscriptions_Users]
GO

-- ==========================================
-- ایجاد جدول referrals
-- ==========================================
CREATE TABLE [dbo].[referrals](
    [id] [int] IDENTITY(1,1) NOT NULL,
    [inviter_id] [int] NOT NULL,
    [referee_telegram_id] [bigint] NOT NULL,
    [status] [nvarchar](20) NOT NULL,
    [created_at] [datetime2](7) NOT NULL,
    [completed_at] [datetime2](7) NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
    CONSTRAINT [UQ_Referrals_RefereeTelegramId] UNIQUE NONCLUSTERED ([referee_telegram_id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_Referrals_Status_Referee] ON [dbo].[referrals](
    [referee_telegram_id] ASC,
    [status] ASC
) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO

ALTER TABLE [dbo].[referrals] ADD CONSTRAINT [DF_Referrals_Status] DEFAULT ('PENDING') FOR [status]
GO
ALTER TABLE [dbo].[referrals] ADD CONSTRAINT [DF_Referrals_CreatedAt] DEFAULT (getdate()) FOR [created_at]
GO

ALTER TABLE [dbo].[referrals] WITH CHECK ADD CONSTRAINT [FK_Referrals_Inviter] FOREIGN KEY([inviter_id]) REFERENCES [dbo].[users] ([id])
GO
ALTER TABLE [dbo].[referrals] CHECK CONSTRAINT [FK_Referrals_Inviter]
GO

-- ==========================================
-- ایجاد جدول user_referral_stats
-- ==========================================
CREATE TABLE [dbo].[user_referral_stats](
    [user_id] [int] NOT NULL,
    [current_points] [int] NOT NULL,
    [total_invites] [int] NOT NULL,
    PRIMARY KEY CLUSTERED ([user_id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[user_referral_stats] ADD CONSTRAINT [DF_UserReferralStats_CurrentPoints] DEFAULT ((0)) FOR [current_points]
GO
ALTER TABLE [dbo].[user_referral_stats] ADD CONSTRAINT [DF_UserReferralStats_TotalInvites] DEFAULT ((0)) FOR [total_invites]
GO

ALTER TABLE [dbo].[user_referral_stats] WITH CHECK ADD CONSTRAINT [FK_UserReferralStats_Users] FOREIGN KEY([user_id]) REFERENCES [dbo].[users] ([id])
GO
ALTER TABLE [dbo].[user_referral_stats] CHECK CONSTRAINT [FK_UserReferralStats_Users]
GO

-- ==========================================
-- ایجاد جدول referral_settings
-- ==========================================
CREATE TABLE [dbo].[referral_settings](
    [id] [int] NOT NULL,
    [required_invites] [int] NOT NULL,
    [gift_package_id] [int] NULL,
    PRIMARY KEY CLUSTERED ([id] ASC) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[referral_settings] ADD CONSTRAINT [DF_ReferralSettings_Id] DEFAULT ((1)) FOR [id]
GO
ALTER TABLE [dbo].[referral_settings] ADD CONSTRAINT [DF_ReferralSettings_RequiredInvites] DEFAULT ((5)) FOR [required_invites]
GO

ALTER TABLE [dbo].[referral_settings] WITH CHECK ADD CONSTRAINT [CK_ReferralSettings_SingleRow] CHECK (([id]=(1)))
GO
ALTER TABLE [dbo].[referral_settings] CHECK CONSTRAINT [CK_ReferralSettings_SingleRow]
GO

-- ==========================================
-- تنظیمات نهایی دیتابیس
-- ==========================================
USE [master]
GO
ALTER DATABASE [NetRah] SET READ_WRITE
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