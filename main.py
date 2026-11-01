import csv
import os
import time
from datetime import datetime

import requests

TOKEN = os.getenv("VK_TOKEN")
GROUP_ID = os.getenv("VK_GROUP_ID")
API_VERSION = "5.199"
API_URL = "https://api.vk.ru/method"
OUTPUT_FILE = "vk_subscribers_check.csv"
USERS_BATCH_SIZE = 100


def api_call(method, **params):
    params.update({
        "access_token": TOKEN,
        "v": API_VERSION,
    })

    response = requests.get(f"{API_URL}/{method}", params=params, timeout=30)
    data = response.json()

    if "error" in data:
        error = data["error"]
        raise RuntimeError(f"Ошибка VK API {error['error_code']}: {error['error_msg']}")

    return data["response"]


def get_member_ids(group_id):
    member_ids = []
    offset = 0

    while True:
        response = api_call(
            "groups.getMembers",
            group_id=group_id,
            offset=offset,
            count=1000,
        )

        items = response.get("items", [])
        total = response.get("count", 0)

        if not items:
            break

        member_ids.extend(items)
        offset += len(items)

        print(f"Получено участников: {len(member_ids)} из {total}")

        if offset >= total:
            break

        time.sleep(0.4)

    return list(dict.fromkeys(member_ids))


def get_status(user):
    deactivated = user.get("deactivated")

    if deactivated == "deleted":
        return "deleted"

    if deactivated == "banned":
        return "banned"

    if not user.get("has_photo"):
        return "no_photo"

    return "ok"


def check_members(member_ids):
    results = []

    for i in range(0, len(member_ids), USERS_BATCH_SIZE):
        batch = member_ids[i:i + USERS_BATCH_SIZE]

        users = api_call(
            "users.get",
            user_ids=",".join(map(str, batch)),
            fields="deactivated,has_photo,last_seen,domain,sex,city",
        )

        users_by_id = {user["id"]: user for user in users}

        for user_id in batch:
            user = users_by_id.get(user_id)

            if user is None:
                results.append({
                    "id": user_id,
                    "domain": "",
                    "name": "",
                    "status": "not_found",
                    "deactivated": "",
                    "has_photo": "",
                    "last_seen": "",
                    "city": "",
                })
                continue

            last_seen = user.get("last_seen", {}).get("time")
            city = user.get("city", {})
            name = f'{user.get("first_name", "")} {user.get("last_name", "")}'.strip()

            results.append({
                "id": user_id,
                "domain": user.get("domain", ""),
                "name": name,
                "status": get_status(user),
                "deactivated": user.get("deactivated", ""),
                "has_photo": user.get("has_photo", 0),
                "last_seen": (
                    datetime.fromtimestamp(last_seen).strftime("%Y-%m-%d %H:%M")
                    if last_seen else ""
                ),
                "city": city.get("title", "") if isinstance(city, dict) else "",
            })

        print(f"Проверено: {min(i + USERS_BATCH_SIZE, len(member_ids))} из {len(member_ids)}")
        time.sleep(0.4)

    return results


def print_summary(results):
    statuses = [row["status"] for row in results]
    total = len(results)

    print("\nРезультаты проверки")
    print(f"Всего участников: {total}")

    for status in ("deleted", "banned", "no_photo", "ok", "not_found"):
        count = statuses.count(status)
        percent = count / total * 100 if total else 0
        print(f"{status}: {count} ({percent:.1f}%)")

    dead_ids = [
        row["id"] for row in results
        if row["status"] in ("deleted", "banned")
    ]

    print("\nУдалённые и заблокированные ID:")
    print(dead_ids)


def save_report(results, filename):
    if not results:
        return

    fields = [
        "id",
        "domain",
        "name",
        "status",
        "deactivated",
        "has_photo",
        "last_seen",
        "city",
    ]

    with open(filename, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)


def main():
    print("Собираем участников сообщества...")

    member_ids = get_member_ids(GROUP_ID)

    if not member_ids:
        print("Не удалось получить участников сообщества.")
        return

    print(f"\nВсего участников: {len(member_ids)}")
    print("Проверяем профили...\n")

    results = check_members(member_ids)

    print_summary(results)
    save_report(results, OUTPUT_FILE)

    print(f"\nОтчёт сохранён в файл: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
