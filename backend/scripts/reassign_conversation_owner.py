"""Explicit, one-owner-at-a-time conversation migration utility."""

import argparse
import uuid

import psycopg
from redis import Redis

from config.settings import settings


CONFIRMATION = "REASSIGN-CONVERSATIONS"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Preview or reassign all conversations from one known owner to another."
    )
    parser.add_argument("--source-owner", required=True, type=uuid.UUID)
    parser.add_argument("--new-owner", required=True, type=uuid.UUID)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.source_owner == args.new_owner:
        raise SystemExit("Source and destination owners must differ.")
    if args.apply and args.confirm != CONFIRMATION:
        raise SystemExit(f"--apply requires --confirm {CONFIRMATION}")

    with psycopg.connect(settings.DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM conversations_schema.conversations WHERE user_id = %s FOR UPDATE",
                (str(args.source_owner),),
            )
            conversation_ids = [str(row[0]) for row in cursor.fetchall()]
            count = len(conversation_ids)
            print(f"Matching conversations: {count}")
            if not args.apply:
                print("Dry run only. No rows changed.")
                connection.rollback()
                return 0
            cache = Redis.from_url(settings.REDIS_URL, decode_responses=True)
            cache.ping()
            cursor.execute(
                """
                UPDATE conversations_schema.conversations
                SET user_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                """,
                (str(args.new_owner), str(args.source_owner)),
            )
            if cursor.rowcount != count:
                connection.rollback()
                raise RuntimeError("Row count changed during migration; transaction rolled back.")
            keys = [f"conversation:{args.source_owner}:{item}" for item in conversation_ids]
            if keys:
                cache.delete(*keys)
        connection.commit()
    print(f"Reassigned conversations: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
