import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import urllib.request
from selenium.webdriver.common.keys import Keys  # Simulate keystrokes

def download_image_fx(prompt, wait_time=15, manual_login_time=60):
    print(f"Setting up browser for prompt: '{prompt}'")

    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    # Ensure persistence of login session
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
    os.makedirs(user_data_dir, exist_ok=True)
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:
        driver.get("https://labs.google/fx/tools/image-fx/")
        print("✅ Navigated to Image FX website")

        # **Step 1: Check for login requirement**
        try:
            sign_in_button = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Sign in with Google')]"))
            )
            if sign_in_button.is_displayed():
                print("🔑 Login required. Please log in manually.")
                print(f"⏳ You have {manual_login_time} seconds to complete the login process...")

                # Monitor login completion
                for i in range(manual_login_time):
                    if i % 5 == 0:
                        try:
                            driver.find_element(By.CSS_SELECTOR, "div[role='textbox']")
                            print("✅ Login detected! Proceeding.")
                            break
                        except:
                            print(f"{manual_login_time - i} seconds remaining for login...")
                    time.sleep(1)
        except:
            print("✅ Sign-in button not found, assuming already logged in.")

        # **Step 2: Locate the Prompt Input Field**
        print("⏳ Waiting for the prompt input field to appear...")
        input_field_xpath = "//div[@role='textbox']"

        prompt_input = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, input_field_xpath))
        )

        # **Step 3: Clear the Field and Remove Hidden Placeholder Text**
        print("📝 Preparing input field...")

        prompt_input.click()  # Ensure the input field is focused
        time.sleep(0.5)  # Small delay before clearing
        prompt_input.send_keys(Keys.CONTROL + "a")  # Select all text
        prompt_input.send_keys(Keys.BACKSPACE)  # Delete selected text

        # **Ensure element is re-fetched after clearing to prevent stale reference**
        prompt_input = driver.find_element(By.XPATH, input_field_xpath)

        # **Step 4: Mimic Human Typing with Delays**
        print("⌨️ Typing the prompt like a human...")

        for char in prompt:
            prompt_input.send_keys(char)
            time.sleep(0.1)  # Small delay between keystrokes

        print(f"✅ Final Input Set: {prompt}")

        # **Step 5: Click the Generate Button**
        print("🔍 Searching for the action button (Create or I'm Feeling Lucky)...")

        button_xpath = "//button[.//div[contains(text(),'Create')] or .//div[contains(text(),\"I'm feeling lucky\")]]"
        action_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, button_xpath))
        )

        print(f"🖱️ Clicking the detected button: {action_button.text}")
        action_button.click()

        # **Step 6: Wait for Image Generation**
        print(f"⏳ Waiting {wait_time} seconds for image generation...")
        time.sleep(wait_time)

        # **Step 7: Locate and Download All Unique Images**
        print("📸 Searching for all generated images inside the grid container...")

        image_elements = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class, 'sc-43d791a1')]//img"))
        )

        if image_elements:
            os.makedirs("downloads", exist_ok=True)

            downloaded_urls = set()
            saved_count = 0

            for img in image_elements:
                image_url = img.get_attribute("src")

                if image_url and image_url not in downloaded_urls:
                    downloaded_urls.add(image_url)  # Track unique images
                    filename = f"downloads/{prompt.replace(' ', '_').replace('/', '_')}_{saved_count+1}_{int(time.time())}.jpg"
                    urllib.request.urlretrieve(image_url, filename)
                    print(f"✅ Image {saved_count+1} saved: {filename}")
                    saved_count += 1

        else:
            print("❌ No images found. Saving a screenshot for debugging.")
            driver.save_screenshot("debug_screenshot.png")

        # **Step 8: Keep Browser Open for Debugging**
        user_input = input("Press Enter to close the browser or type 'wait' to keep it open: ")
        if user_input.lower() == 'wait':
            print("📌 Keeping browser open. Close manually when done.")
            while True:
                time.sleep(10)

    except Exception as e:
        print(f"❌ An error occurred: {str(e)}")
        driver.save_screenshot("error_screenshot.png")
        print("🛠️ Error screenshot saved for debugging.")

    finally:
        if 'user_input' not in locals() or user_input.lower() != 'wait':
            print("🛑 Closing browser")
            driver.quit()


if __name__ == "__main__":
    prompt = input("Enter your image prompt: ")
    wait_time = int(input("Enter wait time for image generation (default 15): ") or "15")
    login_time = int(input("Enter time for manual login (default 60): ") or "60")
    download_image_fx(prompt, wait_time=wait_time, manual_login_time=login_time)
