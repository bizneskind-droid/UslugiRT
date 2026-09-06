import json
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def get_policies(pth, cookies):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            
        )
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        page.goto("https://uslugi.tatarstan.ru/mis/tatarstan/init")
        page.wait_for_url("**/source**")

        policies = page.locator("#select_polis option")

        result = {}

        for i in range(policies.count()):
            option = policies.nth(i)
            value = option.get_attribute("value")
            if value:
                result[value] = option.text_content()

        policy_path = pth / "policy.json"
        with policy_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)


def setup():
    pth = Path(".data")
    pth.mkdir(parents=True, exist_ok=True)

    phone_number = input("Введите номер телефона: +7").strip()
    password = input("Введите пароль: ").strip()

    with httpx.Client(follow_redirects=True) as client:
        response = client.get("https://uslugi.tatarstan.ru/user/login?callback_url=/")
        
        response = client.get("https://auth-uslugi.tatar.ru/portal/login/phone")
        soup = BeautifulSoup(response.text, "html.parser")
        csrf = soup.select_one('input[name^="__csrf_"]')
        
        if csrf is None:
            raise RuntimeError("CSRF не найден")

        csrf_name = str(csrf["name"])
        csrf_value = str(csrf["value"])
        
        password_data = {
        csrf_name: csrf_value,
        "login_form_model[phone_number]": phone_number,
        "login_form_model[password]": password,
        }
        
        response = client.post("https://auth-uslugi.tatar.ru/portal/login/phone")
        response = client.post(
            "https://auth-uslugi.tatar.ru/portal/login/password",
            data=password_data,
        )
        
        cookies = []
        for cookie in client.cookies.jar:
            cookies.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                }
            )
            
        get_policies(pth, cookies)

        cookies_path = pth / 'user.json'
        with cookies_path.open("w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=4)
  
  

if __name__ == "__main__":
    setup()
