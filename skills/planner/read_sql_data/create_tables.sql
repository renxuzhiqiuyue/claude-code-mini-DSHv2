-- 以旧换新业务库建表语句（本 Skill 权威 DDL）
-- 权威字段以下列为准；线上不一致时再 sql_db_table_schema
SET NAMES utf8mb4;

-- ========== 发卡机构维度表 ==========
DROP TABLE IF EXISTS `iss_ins_dim`;
CREATE TABLE `iss_ins_dim` (
  `iss_ins_id_cd` VARCHAR(32)  NOT NULL COMMENT '发卡机构代码',
  `iss_ins_nm`    VARCHAR(256) NULL     COMMENT '发卡机构中文名称',
  `root_ins_cd`   VARCHAR(32)  NULL     COMMENT '根机构代码',
  `root_ins_nm`   VARCHAR(256) NULL     COMMENT '根机构名称',
  `ins_cata_id1`  VARCHAR(16)  NULL     COMMENT '机构大类代码',
  `ins_cata_nm1`  VARCHAR(128) NULL     COMMENT '机构大类名称',
  `ins_cata_id2`  VARCHAR(16)  NULL     COMMENT '机构中类代码',
  `ins_cata_nm2`  VARCHAR(128) NULL     COMMENT '机构中类名称',
  `ins_cata_id3`  VARCHAR(16)  NULL     COMMENT '机构小类代码',
  `ins_cata_nm3`  VARCHAR(128) NULL     COMMENT '机构小类名称',
  PRIMARY KEY (`iss_ins_id_cd`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='发卡机构维度表';

-- ========== 用户维度表 ==========
DROP TABLE IF EXISTS `usr_dim`;
CREATE TABLE `usr_dim` (
  `usr_id`        VARCHAR(32)  NOT NULL COMMENT '用户 ID',
  `usr_city_nm`   VARCHAR(64)  NULL     COMMENT '城市',
  `branch_org_cd` VARCHAR(32)  NULL     COMMENT '分公司代码',
  `branch_org_nm` VARCHAR(128) NULL     COMMENT '分公司名称',
  `age`           TINYINT      NULL     COMMENT '年龄',
  `sex`           CHAR(2)      NULL     COMMENT '性别',
  `trans_level`   VARCHAR(16)  NULL     COMMENT '交易水平',
  PRIMARY KEY (`usr_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户维度表';

-- ========== 商户维度表 ==========
DROP TABLE IF EXISTS `mchnt_dim`;
CREATE TABLE `mchnt_dim` (
  `mchnt_cd`      VARCHAR(16)  NOT NULL COMMENT '商编',
  `mchnt_nm`      VARCHAR(128) NULL     COMMENT '商户名称',
  `mchnt_city_nm` VARCHAR(64)  NULL     COMMENT '所属城市',
  `acq_ins_id_cd` VARCHAR(32)  NULL     COMMENT '收单机构代码',
  `acq_ins_nm`    VARCHAR(256) NULL     COMMENT '收单机构名称',
  PRIMARY KEY (`mchnt_cd`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商户维度表';

-- ========== 卡号信息表 ==========
DROP TABLE IF EXISTS `card_info`;
CREATE TABLE `card_info` (
  `card_no`       CHAR(16)     NOT NULL COMMENT '卡号',
  `usr_id`        VARCHAR(32)  NULL     COMMENT '用户 ID',
  `iss_ins_id_cd` VARCHAR(32)  NULL     COMMENT '发卡机构代码',
  `card_attr`     VARCHAR(32)  NULL     COMMENT '卡性质',
  `card_brand`    VARCHAR(64)  NULL     COMMENT '卡品牌',
  PRIMARY KEY (`card_no`),
  KEY `idx_card_info_usr_id` (`usr_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='卡号信息表';

-- ========== 以旧换新交易明细表（事实表） ==========
DROP TABLE IF EXISTS `yjhx_trans_detail`;
CREATE TABLE `yjhx_trans_detail` (
  `issuer_tp`     VARCHAR(32)   NULL COMMENT '发券方',
  `mchnt_cd`      VARCHAR(16)   NULL COMMENT '商编',
  `usr_id`        VARCHAR(32)   NULL COMMENT '用户 ID',
  `card_no`       CHAR(16)      NULL COMMENT '卡号',
  `iss_ins_id_cd` VARCHAR(32)   NULL COMMENT '发卡机构代码',
  `prod_nm`       VARCHAR(128)  NULL COMMENT '商品名称',
  `prod_tp`       VARCHAR(32)   NULL COMMENT '商品大类',
  `eng_grade`     VARCHAR(16)   NULL COMMENT '能级分类',
  `brand_nm`      VARCHAR(64)   NULL COMMENT '品牌名称',
  `act_id`        VARCHAR(16)   NULL COMMENT '活动 ID',
  `act_nm`        VARCHAR(128)  NULL COMMENT '活动名称',
  `rec_city_nm`   VARCHAR(64)   NULL COMMENT '收货城市',
  `rec_dt`        DATE          NULL COMMENT '收货日期',
  `trans_amt`     DECIMAL(12,2) NULL COMMENT '交易金额',
  `discount_amt`  DECIMAL(10,2) NULL COMMENT '补贴金额',
  `income_amt`    DECIMAL(10,2) NULL COMMENT '收入金额',
  `trans_dt`      DATE          NULL COMMENT '交易日期（月报主时间字段，YYYY-MM-DD）',
  `trans_tm`      TIME          NULL COMMENT '交易时间',
  `pay_tp`        VARCHAR(32)   NULL COMMENT '支付方式',
  `is_payment`    CHAR(2)       NULL COMMENT '是否分期',
  `is_online`     CHAR(2)       NULL COMMENT '是否线上',
  KEY `idx_yjhx_usr_id` (`usr_id`),
  KEY `idx_yjhx_mchnt_cd` (`mchnt_cd`),
  KEY `idx_yjhx_trans_dt` (`trans_dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='以旧换新交易明细表';
