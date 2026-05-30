-- PostgreSQL 初始化脚本：启用必要扩展
-- 此文件在 PostgreSQL 容器首次启动时自动执行

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";

-- Apache AGE 扩展（图存储）
-- M1-M3 期间用 PostgreSQL 递归 CTE 模拟图遍历
-- M4 Stage 4.1 正式引入 AGE
-- CREATE EXTENSION IF NOT EXISTS "age";
-- SET search_path = ag_catalog, "$user", public;
