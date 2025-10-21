from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `agent_runs` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `chat_id` INT NOT NULL,
    `user_id` VARCHAR(191) NOT NULL,
    `agent` VARCHAR(64) NOT NULL,
    `router_confidence` DOUBLE,
    `user_message` LONGTEXT NOT NULL,
    `final_reply` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `tool_events` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `tool_name` VARCHAR(64) NOT NULL,
    `args_json` LONGTEXT,
    `result_json` LONGTEXT,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `run_id` INT NOT NULL,
    CONSTRAINT `fk_tool_eve_agent_ru_981c33b1` FOREIGN KEY (`run_id`) REFERENCES `agent_runs` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `tool_events`;
        DROP TABLE IF EXISTS `agent_runs`;"""
