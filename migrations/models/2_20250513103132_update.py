from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `calltranscription` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `lead_id` INT NOT NULL,
    `transcription` LONGTEXT NOT NULL,
    `call_date` DATETIME(6) NOT NULL,
    `duration` INT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `leadscore` (
    `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `lead_id` INT NOT NULL,
    `intent_score` DOUBLE NOT NULL,
    `tone_score` DOUBLE NOT NULL,
    `urgency_score` DOUBLE NOT NULL,
    `overall_score` DOUBLE NOT NULL,
    `analysis_summary` LONGTEXT NOT NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    `transcription_id_id` INT NOT NULL,
    CONSTRAINT `fk_leadscor_calltran_a847f94f` FOREIGN KEY (`transcription_id_id`) REFERENCES `calltranscription` (`id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `calltranscription`;
        DROP TABLE IF EXISTS `leadscore`;"""
