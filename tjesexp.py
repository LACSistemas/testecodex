from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException, StaleElementReferenceException
import time
import os
import re
import json
import tempfile
from datetime import datetime
from pathlib import Path

class PJEDaycovalAutomationESCitacao:

    def __init__(self, party_filter=None, headless=False):
        """Initialize the PJE TJES automation system - Citação search version

        Args:
            party_filter: Nome da parte para filtrar (None = todos os processos)
            headless: Executar em modo headless
        """
        self.driver = None
        self.wait = None
        self.headless = headless
        self.original_window = None

        # Configuração de filtro
        self.party_filter = party_filter

        # Report data structure
        self.report_data = {}

        # Create session folder for reports - TJES Citação search
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        party_label = self.party_filter or "todas_partes"
        self.session_folder = f"{party_label}_tjes_citacao_{timestamp}"
        self.report_dir = os.path.join(os.getcwd(), "reports_tjes_citacao", self.session_folder)
        os.makedirs(self.report_dir, exist_ok=True)

        # Live report file paths
        self.live_report_txt = os.path.join(self.report_dir, f"relatorio_{party_label}_tjes_citacao_live.txt")
        self.live_report_json = os.path.join(self.report_dir, f"relatorio_{party_label}_tjes_citacao_live.json")

        print(f"📁 Session report folder: {self.report_dir}")
        print(f"🔍 Party filter: {self.party_filter or 'NONE (all parties)'}")
        print(f"🔍 Search mode: Looking for 'Citação' in Expedientes")
    
    def setup_driver(self):
        """Setup Chrome driver with an automatic fallback for renderer crashes"""
        # Keep a dedicated temporary profile per run to avoid profile corruption issues.
        # This helps on environments where Chrome starts crashing with STATUS_ACCESS_VIOLATION.
        temp_profile_dir = tempfile.mkdtemp(prefix="selenium_tjes_")

        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")

        # Chrome download preferences
        prefs = {
            "download.default_directory": os.getcwd(),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)

        # Additional Chrome options for stability
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Options to prevent window from popping up and stealing focus
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-component-extensions-with-background-pages")

        # Extra hardening for STATUS_ACCESS_VIOLATION / renderer instability
        chrome_options.add_argument(f"--user-data-dir={temp_profile_dir}")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-features=RendererCodeIntegrity")
        chrome_options.add_argument("--no-zygote")
        chrome_options.add_argument("--remote-debugging-pipe")

        print("🚀 Starting Chrome browser...")
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
        except WebDriverException as first_error:
            print(f"⚠️ First Chrome start failed: {first_error}")
            print("🔁 Retrying Chrome startup with conservative fallback flags...")
            chrome_options.add_argument("--disable-features=VizDisplayCompositor")
            chrome_options.add_argument("--disable-features=UseSkiaRenderer")
            self.driver = webdriver.Chrome(options=chrome_options)

        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, 30)
        # Removed maximize_window() to prevent focus stealing
        
        # Store the original window handle
        self.original_window = self.driver.current_window_handle

        # Diagnostic output (helps identify browser/driver incompatibility)
        try:
            caps = self.driver.capabilities or {}
            browser_version = caps.get("browserVersion", "unknown")
            chrome_driver_version = (caps.get("chrome", {}) or {}).get("chromedriverVersion", "unknown")
            print(f"🧩 Browser version: {browser_version}")
            print(f"🧩 ChromeDriver version: {chrome_driver_version}")
        except Exception as e:
            print(f"⚠️ Could not collect driver diagnostics: {str(e)}")

        # Set page load timeout
        self.driver.set_page_load_timeout(60)
    
    def handle_alert_if_present(self):
        """Handle JavaScript alerts if they appear"""
        try:
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            print(f"🚨 Alert detected: {alert_text}")
            alert.accept()
            print("✅ Alert accepted")
            time.sleep(1)
            return True
        except:
            return False
    
    def check_for_captcha_and_pause(self):
        """Check for CAPTCHA and pause for manual intervention if found"""
        try:
            # Common CAPTCHA selectors for PJE systems
            captcha_selectors = [
                (By.XPATH, "//img[contains(@src, 'captcha')]"),
                (By.XPATH, "//img[contains(@alt, 'captcha')]"),
                (By.XPATH, "//img[contains(@id, 'captcha')]"),
                (By.XPATH, "//div[contains(@class, 'captcha')]"),
                (By.XPATH, "//input[contains(@placeholder, 'captcha')]"),
                (By.XPATH, "//input[contains(@name, 'captcha')]"),
                (By.XPATH, "//label[contains(text(), 'Captcha')]"),
                (By.XPATH, "//label[contains(text(), 'CAPTCHA')]"),
            ]
            
            captcha_found = False
            for selector_type, selector_value in captcha_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector_value)
                    for element in elements:
                        if element.is_displayed():
                            captcha_found = True
                            break
                    if captcha_found:
                        break
                except:
                    continue
            
            if captcha_found:
                print("\n" + "="*60)
                print("🔒 CAPTCHA DETECTED - MANUAL INTERVENTION REQUIRED")
                print("="*60)
                print("A CAPTCHA has been detected on the current page.")
                print("Please solve the CAPTCHA manually and then press ENTER to continue.")
                print("="*60)
                input("\n✋ Press ENTER after solving the CAPTCHA: ")
                print("✅ Continuing automation after CAPTCHA resolution...")
                time.sleep(2)
                return True
            
            return False
            
        except Exception as e:
            print(f"⚠️ Error checking for CAPTCHA: {str(e)}")
            return False
    
    def safe_click(self, element, use_js=False):
        """Safely click an element with error handling"""
        try:
            if use_js:
                self.driver.execute_script("arguments[0].click();", element)
            else:
                element.click()
            time.sleep(0.5)
            self.handle_alert_if_present()
            return True
        except Exception as e:
            print(f"❌ Click failed: {str(e)}")
            return False
    
    def wait_for_manual_navigation_to_acervo(self):
        """Wait for manual navigation to Acervo page"""
        print("\n" + "="*60)
        print("⚠️ MANUAL NAVIGATION REQUIRED")
        print("="*60)
        print("Please manually:")
        print("1. Complete the login (with CAPTCHA if present)")
        print("2. Click on ACERVO in the navigation menu")
        print("3. Wait for the page with comarcas list to load")
        print("   (You should see the list of comarcas on the left side)")
        print("5. Press ENTER here when you're on the Acervo page")
        print("="*60)
        
        input("\n✋ Press ENTER when you're on the Acervo page with comarcas visible: ")
        print("✅ Continuing automation...")
        time.sleep(2)
        
        # Verify we're on the right page
        current_url = self.driver.current_url
        print(f"📍 Current URL: {current_url}")
        
        return True
    
    def simplified_login_and_navigate(self):
        """Simplified approach - just open the login page and wait for manual navigation"""
        try:
            login_url = "https://pje.tjes.jus.br/pje/login.seam"
            print(f"📍 Opening TJES login page: {login_url}")
            self.driver.get(login_url)
            
            # Check for CAPTCHA before proceeding
            self.check_for_captcha_and_pause()
            
            # Wait for manual navigation to Acervo
            self.wait_for_manual_navigation_to_acervo()
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def go_to_first_page(self):
        """Navigate to the first page of results"""
        try:
            print("📄 Checking if we need to go to first page...")
            
            # Look for the "go to first page" button
            first_page_selectors = [
                (By.XPATH, "//td[@class=' rich-datascr-button' and @onclick=\"Event.fire(this, 'rich:datascroller:onscroll', {'page': 'first'});\"]"),
                (By.XPATH, "//td[contains(@class, 'rich-datascr-button') and contains(@onclick, \"'page': 'first'\")]"),
                (By.XPATH, "//td[contains(@onclick, 'first') and text()='««']"),
                (By.XPATH, "//td[text()='««']"),
                (By.XPATH, "//a[text()='««']"),
                (By.XPATH, "//span[text()='««']"),
            ]
            
            first_button = None
            for selector_type, selector_value in first_page_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector_value)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            first_button = element
                            break
                    if first_button:
                        break
                except:
                    continue
            
            if first_button:
                print("📄 Found 'Go to first page' button, clicking...")
                try:
                    first_button.click()
                    print("✅ Navigated to first page")
                    time.sleep(3)
                    return True
                except:
                    try:
                        self.driver.execute_script("arguments[0].click();", first_button)
                        print("✅ Navigated to first page (JS)")
                        time.sleep(3)
                        return True
                    except:
                        try:
                            self.driver.execute_script("Event.fire(arguments[0], 'rich:datascroller:onscroll', {'page': 'first'});", first_button)
                            print("✅ Navigated to first page (Event)")
                            time.sleep(3)
                            return True
                        except:
                            pass
            else:
                print("📊 Already on first page or pagination not available")
                
            return False
            
        except Exception as e:
            print(f"⚠️ Error navigating to first page: {str(e)}")
            return False
    
    def search_party_in_comarca(self):
        """Click search button, input party name in field, and search (or skip if no filter)"""
        try:
            # Se não há filtro, não fazer nada
            if self.party_filter is None:
                print("🔍 No party filter - processing ALL parties")
                return True

            print(f"🔍 Setting up party search filter for: {self.party_filter}")
            time.sleep(2)
            
            # Step 1: Find and click the search icon button
            search_icon_selectors = [
                (By.XPATH, "//a[@title='Pesquisar nesta caixa']"),
                (By.XPATH, "//a[@class='btn-menu-abas dropdown-toggle' and @title='Pesquisar nesta caixa']"),
                (By.XPATH, "//a[contains(@title, 'Pesquisar nesta caixa')]"),
                (By.XPATH, "//a[.//i[@class='fa fa-search fa-lg']]"),
                (By.XPATH, "//a[@data-toggle='dropdown' and .//i[contains(@class, 'fa-search')]]"),
                (By.CSS_SELECTOR, "a.btn-menu-abas.dropdown-toggle"),
                (By.CSS_SELECTOR, "a[title*='Pesquisar']"),
            ]
            
            search_icon = None
            for selector_type, selector_value in search_icon_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector_value)
                    for element in elements:
                        if element.is_displayed():
                            search_icon = element
                            print("✅ Found search button with title 'Pesquisar nesta caixa'")
                            break
                    if search_icon:
                        break
                except:
                    continue
            
            if not search_icon:
                print("❌ Could not find search button")
                return False
            
            # Click the search button to open dropdown/modal
            print("🎯 Clicking search button to open search form...")
            try:
                search_icon.click()
                print("✅ Clicked search button")
            except:
                try:
                    self.driver.execute_script("arguments[0].click();", search_icon)
                    print("✅ Clicked search button (JavaScript)")
                except:
                    try:
                        self.driver.execute_script("$(arguments[0]).dropdown('toggle');", search_icon)
                        print("✅ Toggled dropdown (jQuery)")
                    except Exception as e:
                        print(f"❌ Failed to click search button: {str(e)}")
                        return False
            
            time.sleep(2)
            
            # Step 2: Find and fill the specific input field
            print("📝 Looking for party name input field...")
            party_name_field = None
            
            try:
                party_name_field = self.driver.find_element(By.ID, "formAcervo:itDestPend")
                if party_name_field.is_displayed():
                    print("✅ Found party name field by exact ID")
                else:
                    party_name_field = None
            except:
                pass
            
            if not party_name_field:
                party_name_selectors = [
                    (By.ID, "formAcervo:itDestPend"),
                    (By.NAME, "formAcervo:itDestPend"),
                    (By.CSS_SELECTOR, "input#formAcervo\\:itDestPend"),
                    (By.XPATH, "//input[@id='formAcervo:itDestPend']"),
                    (By.XPATH, "//input[@name='formAcervo:itDestPend']"),
                    (By.XPATH, "//input[@class='campoPesquisa' and @title='Informe o nome da parte.']"),
                    (By.XPATH, "//input[@title='Informe o nome da parte.']"),
                    (By.CSS_SELECTOR, "input.campoPesquisa"),
                ]
                
                for selector_type, selector_value in party_name_selectors:
                    try:
                        element = self.driver.find_element(selector_type, selector_value)
                        if element.is_displayed() and element.is_enabled():
                            party_name_field = element
                            print(f"✅ Found party name field using {selector_type}")
                            break
                    except:
                        continue
            
            if not party_name_field:
                print("❌ Could not find party name input field")
                return False
            
            # Clear and fill the field with the party name
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", party_name_field)
                time.sleep(0.5)
                party_name_field.clear()
                self.driver.execute_script("arguments[0].value = '';", party_name_field)
                time.sleep(0.5)
                party_name_field.send_keys(self.party_filter)
                print(f"✅ Entered '{self.party_filter}' in party name field")
                time.sleep(1)
            except Exception as e:
                print(f"❌ Error filling party name field: {str(e)}")
                return False
            
            # Step 3: Click the PESQUISAR button
            print("🔎 Looking for PESQUISAR button...")
            search_button = None
            
            try:
                search_button = self.driver.find_element(By.ID, "formAcervo:btPesqAc")
                if search_button.is_displayed():
                    print("✅ Found PESQUISAR button by exact ID")
                else:
                    search_button = None
            except:
                pass
            
            if not search_button:
                search_button_selectors = [
                    (By.ID, "formAcervo:btPesqAc"),
                    (By.NAME, "formAcervo:btPesqAc"),
                    (By.CSS_SELECTOR, "input#formAcervo\\:btPesqAc"),
                    (By.XPATH, "//input[@id='formAcervo:btPesqAc']"),
                    (By.XPATH, "//input[@name='formAcervo:btPesqAc']"),
                    (By.XPATH, "//input[@value='Pesquisar' and contains(@class, 'btn-primary')]"),
                    (By.XPATH, "//input[@value='Pesquisar']"),
                    (By.CSS_SELECTOR, "input.btn.btn-primary[value='Pesquisar']"),
                ]
                
                for selector_type, selector_value in search_button_selectors:
                    try:
                        element = self.driver.find_element(selector_type, selector_value)
                        if element.is_displayed() and element.is_enabled():
                            search_button = element
                            print(f"✅ Found PESQUISAR button using {selector_type}")
                            break
                    except:
                        continue
            
            if search_button:
                try:
                    search_button.click()
                    print("✅ Clicked PESQUISAR button")
                except:
                    try:
                        self.driver.execute_script("arguments[0].click();", search_button)
                        print("✅ Clicked PESQUISAR button (JavaScript)")
                    except:
                        party_name_field.send_keys(Keys.RETURN)
                        print("✅ Pressed Enter to search (fallback)")
            else:
                print("⚠️ Could not find PESQUISAR button, pressing Enter...")
                party_name_field.send_keys(Keys.RETURN)
                print("✅ Pressed Enter to search")
            
            print("⏳ Waiting for search results to load...")
            time.sleep(5)
            
            # After search, go to first page to ensure we start from the beginning
            self.go_to_first_page()
            
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                if self.party_filter.upper() in page_text.upper():
                    print(f"✅ Filter applied successfully - found '{self.party_filter}' processes")
                    return True
                elif "resultado" in page_text.lower() and "encontrado" in page_text.lower():
                    if "0" in page_text or "nenhum" in page_text.lower():
                        print(f"⚠️ Filter applied but no '{self.party_filter}' processes found in this comarca")
                    else:
                        print("✅ Filter applied - results found")
                    return True
                else:
                    print("⚠️ Filter status uncertain - continuing anyway")
                    return True
            except:
                print("⚠️ Could not verify filter results")
                return True

        except Exception as e:
            print(f"❌ Error setting up party search: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_comarca_list(self):
        """Get list of all comarcas from the left panel"""
        try:
            print("📋 Getting list of comarcas...")
            
            # Known list of all comarcas in Espírito Santo
            known_comarcas = [
                "Afonso Cláudio", "Alegre", "Alfredo Chaves", "Anchieta", "Apiacá", "Aracruz", "Baixo Guandu", "Barra de São Francisco",
                "Boa Esperança", "Bom Jesus do Norte", "Cachoeiro de Itapemirim", "Cariacica", "Castelo", "Colatina", "Conceição da Barra",
                "Conceição do Castelo", "Domingos Martins", "Dores do Rio Preto", "Ecoporanga", "Guaçuí", "Guarapari", "Ibiraçu", "Iconha",
                "Itaguaçu", "Itapemirim", "Itarana", "Iúna", "Jerônimo Monteiro", "Linhares", "Mantenópolis", "Mimoso do Sul",
                "Montanha", "Mucurici", "Vitória", "Vila Velha", "Muqui", "Muniz Freire", "Nova Venécia", "Pancas", "Pinheiros", "Presidente Kennedy",
                "Rio Novo do Sul", "Santa Leopoldina", "Santa Teresa", "São Gabriel da Palha", "São José do Calçado", "São Mateus", "Serra",
                "Venda Nova do Imigrante", "Viana", "Pedro Canário", "Rio Bananal", "Alto Rio Novo", "São Domingos do Norte", "Marechal Floriano",
                "Santa Maria de Jetibá", "Águia Branca", "Ibitirama", "Fundão", "Atílio Vivacqua", "Vargem Alta", "Piúma", "Laranja da Terra",
                "Ibatiba", "Jaguaré", "Marilândia", "João Neiva", "Água Doce do Norte", "Marataízes"
            ]
            
            time.sleep(3)
            
            # First, try to expand the tree if needed
            print("🔍 Looking for comarca tree to expand...")
            expand_selectors = [
                (By.XPATH, "//span[@class='ui-icon ui-icon-triangle-1-e']"),
                (By.XPATH, "//span[contains(@class, 'ui-treenode-icon') and contains(@class, 'ui-icon-triangle')]"),
                (By.XPATH, "//div[@class='ui-tree-toggler']//span[contains(@class, 'ui-icon')]"),
                (By.XPATH, "//a[contains(@class, 'ui-tree-toggler')]"),
            ]
            
            for selector_type, selector_value in expand_selectors:
                try:
                    expand_elements = self.driver.find_elements(selector_type, selector_value)
                    if expand_elements:
                        print(f"📂 Found {len(expand_elements)} tree nodes to expand")
                        for expand_elem in expand_elements[:5]:
                            try:
                                if expand_elem.is_displayed():
                                    expand_elem.click()
                                    time.sleep(0.5)
                            except:
                                pass
                        break
                except:
                    continue
            
            # Now look for comarcas with multiple selector strategies
            found_comarcas = []
            comarca_selectors = [
                (By.XPATH, "//span[@class='ui-treenode-label']"),
                (By.XPATH, "//span[contains(@class, 'ui-treenode-label')]"),
                (By.CSS_SELECTOR, ".ui-treenode-label"),
                (By.CSS_SELECTOR, "span.ui-treenode-label"),
                (By.XPATH, "//li[contains(@class, 'ui-treenode')]//span[contains(@class, 'ui-treenode-label')]"),
                (By.XPATH, "//div[@id='formAbaAcervo:trAc']//span[@class='ui-treenode-label']"),
                (By.XPATH, "//form[@id='formAbaAcervo']//span[@class='ui-treenode-label']"),
                (By.XPATH, "//a[contains(@id, 'formAbaAcervo')]//span"),
                (By.XPATH, "//a[@class='ui-treenode-content']//span"),
            ]
            
            print("🔍 Searching for comarcas with multiple strategies...")
            for selector_type, selector_value in comarca_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector_value)
                    print(f"  Found {len(elements)} elements with {selector_type}")
                    for element in elements:
                        try:
                            if element.is_displayed():
                                text = element.text.strip()
                                if text in known_comarcas and text not in found_comarcas:
                                    found_comarcas.append(text)
                                    print(f"    ✅ Found comarca: {text}")
                        except:
                            continue
                except Exception as e:
                    continue
            
            if len(found_comarcas) == 0:
                print("⚠️ No comarcas found with selectors, trying alternative approach...")
                try:
                    tree_elements = self.driver.find_elements(By.XPATH, "//div[contains(@id, 'formAbaAcervo')]//span")
                    for element in tree_elements:
                        try:
                            text = element.text.strip()
                            if text in known_comarcas and text not in found_comarcas:
                                found_comarcas.append(text)
                        except:
                            continue
                except:
                    pass
            
            if len(found_comarcas) == 0:
                print("⚠️ Could not find comarcas in the page. Will use known list.")
                print("⚠️ Please make sure you are on the ACERVO page with the comarca tree visible!")
                found_comarcas = known_comarcas
            
            # Sort to match original order
            found_comarcas = [c for c in known_comarcas if c in found_comarcas]
            
            print(f"📊 Found {len(found_comarcas)} total comarcas")
            if len(found_comarcas) > 0:
                print(f"📝 First comarcas to process: {', '.join(found_comarcas[:5])}")
            
            return found_comarcas
            
        except Exception as e:
            print(f"❌ Error getting comarca list: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def click_comarca(self, comarca_name):
        """Click on a specific comarca (ES PJE doesn't need Caixa de entrada - you're already inside after clicking)"""
        try:
            print(f"🎯 Clicking on comarca: {comarca_name}")
            
            # First click on the comarca to expand it
            comarca_selectors = [
                (By.XPATH, f"//span[normalize-space(text())='{comarca_name}']"),
                (By.XPATH, f"//span[text()='{comarca_name}']"),
                (By.XPATH, f"//a[contains(text(), '{comarca_name}')]"),
                (By.XPATH, f"//li[contains(@class, 'ui-treenode')]//span[normalize-space()='{comarca_name}']"),
            ]
            
            comarca_element = None
            for selector_type, selector_value in comarca_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector_value)
                    for element in elements:
                        if element.is_displayed():
                            comarca_element = element
                            break
                    if comarca_element:
                        break
                except:
                    continue
            
            if not comarca_element:
                print(f"❌ Could not find comarca: {comarca_name}")
                return False
            
            # Click on the comarca (in ES PJE, this takes you directly inside)
            try:
                comarca_element.click()
                print(f"✅ Clicked on comarca: {comarca_name}")
            except:
                try:
                    self.driver.execute_script("arguments[0].click();", comarca_element)
                    print(f"✅ Clicked on comarca (JS): {comarca_name}")
                except:
                    print(f"❌ Failed to click comarca")
                    return False
            
            time.sleep(3)
            
            # Go to first page immediately after clicking comarca
            print("📄 Going to first page immediately after opening comarca...")
            self.go_to_first_page()
            
            print("✅ Comarca selected, navigated to first page")
            return True
            
        except Exception as e:
            print(f"❌ Error clicking comarca {comarca_name}: {str(e)}")
            return False
    
    def find_process_links_on_current_page(self):
        """Find all process links on the current page with their information"""
        try:
            time.sleep(2)
            
            # First, find all process rows/containers
            row_selectors = [
                (By.XPATH, "//div[contains(@class, 'vcenter') and .//a[contains(@class, 'numero-processo-acervo')]]"),
                (By.XPATH, "//div[contains(@class, 'row') and .//a[contains(text(), 'CumSen') or contains(text(), 'BAAF') or contains(text(), 'ExTiEx')]]"),
                (By.XPATH, "//tr[.//a[contains(@onclick, 'consultaProcessual')]]"),
            ]
            
            found_elements = []
            found_texts = set()
            
            for selector_type, selector_value in row_selectors:
                try:
                    row_elements = self.driver.find_elements(selector_type, selector_value)
                    for row in row_elements:
                        if row.is_displayed():
                            # Check if this row contains "ARQUIVADO" in visible text
                            row_text = row.text.upper()
                            is_archived = 'ARQUIVADO' in row_text
                            
                            # Find the process link within this row
                            link_selectors = [
                                (By.XPATH, ".//a[contains(@class, 'numero-processo-acervo')]"),
                                (By.XPATH, ".//a[contains(@onclick, 'consultaProcessual')]"),
                                (By.XPATH, ".//a[contains(@href, 'consultaProcessual')]"),
                                (By.XPATH, ".//a[contains(text(), 'CumSen') or contains(text(), 'BAAF') or contains(text(), 'ExTiEx')]"),
                            ]
                            
                            process_link = None
                            for link_selector_type, link_selector_value in link_selectors:
                                try:
                                    links = row.find_elements(link_selector_type, link_selector_value)
                                    for link in links:
                                        if link.is_displayed():
                                            text = link.text.strip()
                                            if text and re.search(r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}', text):
                                                process_link = link
                                                break
                                    if process_link:
                                        break
                                except:
                                    continue
                            
                            if process_link:
                                text = process_link.text.strip()
                                if text not in found_texts:
                                    # Parse additional info from the row
                                    info = self.parse_process_row_info(row)
                                    info["is_archived"] = is_archived
                                    
                                    found_elements.append({
                                        "text": text,
                                        "element": process_link,
                                        "info": info,
                                        "row_element": row
                                    })
                                    found_texts.add(text)
                    
                    if found_elements:  # If we found elements with this selector, stop trying others
                        break
                except:
                    continue
            
            print(f"📊 Found {len(found_elements)} unique processes on this page")
            return found_elements
            
        except Exception as e:
            print(f"❌ Error finding processes on page: {str(e)}")
            return []
    
    def parse_process_row_info(self, row_element):
        """Parse process information from a row element"""
        try:
            row_text = row_element.text
            info = {
                "parties": "",
                "court": "",
                "distributed": "",
                "last_movement": "",
                "is_archived": False
            }
            
            lines = row_text.split('\n')
            for line in lines:
                line = line.strip()
                if 'X' in line and not line.startswith('/'):
                    info["parties"] = line
                elif line.startswith('/'):
                    info["court"] = line
                elif 'Distribuído em' in line:
                    info["distributed"] = line
                elif 'Último movimento' in line:
                    info["last_movement"] = line
                elif 'ARQUIVADO' in line.upper():
                    info["is_archived"] = True
            
            return info
            
        except Exception as e:
            print(f"⚠️ Could not parse process row info: {str(e)}")
            return {"parties": "", "court": "", "distributed": "", "last_movement": "", "is_archived": False}
    
    def switch_to_ng_frame(self):
        """Switch to the ngFrame iframe that contains the Angular application"""
        try:
            # First switch back to default content
            self.driver.switch_to.default_content()
            
            # Find and switch to the ngFrame iframe
            iframe = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "ngFrame"))
            )
            self.driver.switch_to.frame(iframe)
            print("✅ Switched to ngFrame iframe")
            return True
        except Exception as e:
            print(f"❌ Could not switch to ngFrame: {str(e)}")
            return False
    
    def switch_to_expediente_frame(self):
        """Switch to the second nested iframe that contains the expediente content"""
        try:
            # First ensure we're in the ngFrame
            if not self.switch_to_ng_frame():
                return False
            
            # Wait longer for the expedientes page to load after clicking the icon
            time.sleep(5)
            
            # Look for any iframe within the ngFrame with retries
            max_attempts = 3
            iframes = []
            for attempt in range(max_attempts):
                try:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    print(f"🔍 Attempt {attempt + 1}: Found {len(iframes)} iframe(s) within ngFrame")
                    
                    if iframes:
                        break
                    else:
                        print(f"⏳ No iframes found yet, waiting... (attempt {attempt + 1}/{max_attempts})")
                        time.sleep(3)
                except Exception as e:
                    print(f"⚠️ Error finding iframes on attempt {attempt + 1}: {str(e)}")
                    time.sleep(3)
            
            if not iframes:
                print("❌ No nested iframes found within ngFrame after all attempts")
                return False
            
            # Try each iframe to find the one with expediente content
            for i, iframe in enumerate(iframes):
                try:
                    print(f"🔍 Trying iframe {i+1}...")
                    self.driver.switch_to.frame(iframe)
                    
                    # Wait for content to load in this iframe
                    time.sleep(2)
                    
                    # Check if this iframe contains expediente content
                    # Look for characteristic elements
                    expediente_indicators = [
                        "processoParteExpedienteMenuGridList",
                        "infoPPE", 
                        "expediente",
                        "citação",
                        "citacao",
                        "rich-table", # Common table structure
                        "j_id" # JSF component IDs
                    ]
                    
                    page_source = self.driver.page_source.lower()
                    matches = [indicator.lower() for indicator in expediente_indicators if indicator.lower() in page_source]
                    
                    if matches:
                        print(f"✅ Found expediente content in iframe {i+1} - indicators: {matches}")
                        
                        # Additional verification - look for table structure
                        try:
                            table_elements = self.driver.find_elements(By.XPATH, "//table | //tr | //td")
                            if table_elements:
                                print(f"✅ Confirmed table structure with {len(table_elements)} elements")
                                return True
                        except:
                            pass
                        
                        return True
                    
                    # If not found, go back to ngFrame and try next iframe
                    self.switch_to_ng_frame()
                        
                except Exception as e:
                    print(f"⚠️ Error checking iframe {i+1}: {str(e)}")
                    # Try to go back to ngFrame
                    try:
                        self.switch_to_ng_frame()
                    except:
                        pass
                    continue
            
            print("❌ No iframe found with expediente content")
            return False
                
        except Exception as e:
            print(f"❌ Error switching to expediente frame: {str(e)}")
            return False
    
    def reset_to_main_content(self):
        """Reset to main content (outside all iframes)"""
        try:
            self.driver.switch_to.default_content()
            print("✅ Reset to main content")
            return True
        except Exception as e:
            print(f"❌ Error resetting to main content: {str(e)}")
            return False
    
    def click_process_by_element(self, process_dict):
        """Click on a specific process element with improved stale element handling"""
        try:
            process_text = process_dict["text"]
            print(f"🎯 Opening process: {process_text}")
            
            # Store current windows
            windows_before = len(self.driver.window_handles)
            
            # Try to click the element with retry logic for stale elements
            element = process_dict["element"]
            clicked = False
            
            # Retry up to 3 times for stale element issues
            for attempt in range(3):
                try:
                    # Check if element is still valid by trying to get its text
                    element_text = element.text
                    if process_text not in element_text:
                        print(f"⚠️ Element text mismatch on attempt {attempt + 1}, trying to refind element...")
                        # Try to refind the element by text
                        element = self.refind_process_element(process_text)
                        if not element:
                            print(f"❌ Could not refind element for process {process_text}")
                            return False
                    
                    # Scroll to element
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(1)
                    
                    # Try to click
                    try:
                        element.click()
                        clicked = True
                        print(f"✅ Clicked on process: {process_text}")
                        break
                    except:
                        try:
                            self.driver.execute_script("arguments[0].click();", element)
                            clicked = True
                            print(f"✅ Clicked on process (JavaScript): {process_text}")
                            break
                        except Exception as click_error:
                            print(f"⚠️ Click attempt {attempt + 1} failed: {str(click_error)}")
                            if attempt == 2:  # Last attempt
                                print(f"❌ All click attempts failed for process: {process_text}")
                                return False
                            time.sleep(1)  # Wait before retry
                            continue
                            
                except Exception as e:
                    error_msg = str(e)
                    if "stale" in error_msg.lower() or "not known in the current browsing context" in error_msg.lower():
                        print(f"🔄 Stale element detected on attempt {attempt + 1}, trying to refind...")
                        # Try to refind the element
                        element = self.refind_process_element(process_text)
                        if not element:
                            print(f"❌ Could not refind stale element for process {process_text}")
                            return False
                        continue
                    else:
                        print(f"❌ Unexpected error on attempt {attempt + 1}: {error_msg}")
                        if attempt == 2:  # Last attempt
                            return False
                        time.sleep(1)
                        continue
            
            if not clicked:
                print(f"❌ Failed to click process after all attempts: {process_text}")
                return False
            
            # Wait for page to load
            time.sleep(5)
            
            # Check if new tab opened
            windows_after = len(self.driver.window_handles)
            if windows_after > windows_before:
                print("🆕 New tab opened, switching...")
                new_window = [w for w in self.driver.window_handles if w != self.original_window][-1]
                self.driver.switch_to.window(new_window)
                time.sleep(3)
                
                # Check for access denied or error page immediately
                try:
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text.upper()
                    if "403" in page_text or "FORBIDDEN" in page_text or "ACESSO NEGADO" in page_text or "ACCESS DENIED" in page_text or "ERROR" in page_text:
                        print(f"🚫 Access denied detected immediately for process {process_text}")
                        print("🔄 Closing error tab and returning to main window...")
                        
                        # Close the error tab immediately and return to main window
                        try:
                            self.driver.close()  # Close current tab with error
                            self.driver.switch_to.window(self.original_window)  # Return to main window
                            print("✅ Closed error tab and returned to main window")
                            time.sleep(1)
                            return False  # Return False to indicate this process failed
                        except Exception as close_error:
                            print(f"❌ Error closing tab: {str(close_error)}")
                            # Try emergency recovery
                            try:
                                remaining_windows = self.driver.window_handles
                                if self.original_window in remaining_windows:
                                    self.driver.switch_to.window(self.original_window)
                                    print("✅ Emergency recovery - back to main window")
                                else:
                                    # If main window is lost, use any available window
                                    if remaining_windows:
                                        self.driver.switch_to.window(remaining_windows[0])
                                        self.original_window = remaining_windows[0]
                                        print("⚠️ Main window lost, using first available window")
                                return False
                            except:
                                print("💀 Complete failure - could not recover")
                                return False
                                
                except Exception as e:
                    print(f"⚠️ Could not check for access denied: {str(e)}")
                    # If we can't even check the page, it might be a serious error
                    print("🔄 Assuming error and closing tab...")
                    try:
                        self.driver.close()
                        self.driver.switch_to.window(self.original_window)
                        print("✅ Closed potentially problematic tab")
                        return False
                    except:
                        print("❌ Could not close tab - continuing anyway")
                
                # If no error detected, proceed normally
                # CRITICAL: Switch to the ngFrame iframe in the new tab
                if not self.switch_to_ng_frame():
                    print("❌ Could not access iframe content - closing tab and returning")
                    try:
                        self.driver.close()
                        self.driver.switch_to.window(self.original_window)
                        print("✅ Closed inaccessible tab and returned to main window")
                        return False
                    except:
                        print("❌ Error closing inaccessible tab")
                        return False
            
            return True
            
        except Exception as e:
            print(f"❌ Error clicking process: {str(e)}")
            return False
    
    def refind_process_element(self, process_text):
        """Try to refind a process element by its text when original becomes stale"""
        try:
            print(f"🔍 Attempting to refind element for process: {process_text}")
            
            # Try different selectors to find the element again
            selectors = [
                (By.XPATH, f"//a[contains(text(), '{process_text}')]"),
                (By.XPATH, f"//a[contains(@class, 'numero-processo-acervo') and contains(text(), '{process_text}')]"),
                (By.LINK_TEXT, process_text),
                (By.PARTIAL_LINK_TEXT, process_text.split()[1] if len(process_text.split()) > 1 else process_text),
            ]
            
            for selector_type, selector_value in selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector_value)
                    for element in elements:
                        if element.is_displayed() and process_text in element.text:
                            print(f"✅ Successfully refound element using {selector_type}")
                            return element
                except Exception as e:
                    continue
            
            print(f"❌ Could not refind element for process: {process_text}")
            return None
            
        except Exception as e:
            print(f"❌ Error trying to refind element: {str(e)}")
            return None
    
    def click_expedientes_icon(self):
        """Click on the Expedientes icon - now looking inside the iframe"""
        try:
            print("✉️ Looking for Expedientes icon to click...")
            
            # Make sure we're in the iframe
            self.switch_to_ng_frame()
            
            # Wait for the Angular app to load
            time.sleep(3)
            
            # Now look for the expedientes icon INSIDE the iframe
            expedientes_selectors = [
                # These selectors should work inside the iframe
                (By.CSS_SELECTOR, "div.expedientes-identity"),
                (By.CSS_SELECTOR, "div.icone-container.expedientes-identity"),
                (By.XPATH, "//div[contains(@class, 'expedientes-identity')]"),
                (By.XPATH, "//div[contains(@class, 'icone-container') and contains(@class, 'expedientes')]"),
                # Try by position (usually 4th icon)
                (By.CSS_SELECTOR, "div.icones-acao-processo > div:nth-child(4)"),
                (By.XPATH, "//div[@class='icones-acao-processo']/div[4]"),
                # Look for toolbar icons
                (By.XPATH, "//toolbar-processo//div[contains(@class, 'expedientes')]"),
                (By.CSS_SELECTOR, "toolbar-processo div.expedientes-identity"),
            ]
            
            expedientes_icon = None
            for selector_type, selector_value in expedientes_selectors:
                try:
                    element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((selector_type, selector_value))
                    )
                    if element.is_displayed():
                        expedientes_icon = element
                        print(f"✅ Found Expedientes icon using {selector_type}: {selector_value}")
                        break
                except:
                    continue
            
            if not expedientes_icon:
                # Try JavaScript inside the iframe
                try:
                    script = """
                    // Look for expedientes icon
                    var icons = document.querySelectorAll('div.icone-container');
                    for (var i = 0; i < icons.length; i++) {
                        if (icons[i].className.includes('expedientes')) {
                            return icons[i];
                        }
                    }
                    // Try by position
                    var container = document.querySelector('div.icones-acao-processo');
                    if (container) {
                        var divs = container.querySelectorAll('div.icone-container');
                        if (divs.length >= 4) {
                            return divs[3]; // 4th icon (0-indexed)
                        }
                    }
                    return null;
                    """
                    expedientes_icon = self.driver.execute_script(script)
                    if expedientes_icon:
                        print("✅ Found Expedientes icon using JavaScript")
                except:
                    pass
            
            if not expedientes_icon:
                print("❌ Could not find Expedientes icon in iframe")
                return False
            
            # Click the icon
            try:
                self.driver.execute_script("arguments[0].click();", expedientes_icon)
                print("✅ Clicked Expedientes icon")
            except:
                try:
                    expedientes_icon.click()
                    print("✅ Clicked Expedientes icon (regular click)")
                except Exception as e:
                    print(f"❌ Failed to click Expedientes icon: {str(e)}")
                    return False
            
            # Wait for navigation
            time.sleep(5)
            
            # Verify we're on expedientes page
            try:
                current_url = self.driver.current_url
                if "expedientes" in current_url.lower() or "expediente" in current_url.lower():
                    print("✅ Navigated to Expedientes page")
                    return True
            except:
                pass
            
            print("⚠️ Clicked icon, proceeding to check for content...")
            return True
            
        except Exception as e:
            print(f"❌ Error clicking Expedientes icon: {str(e)}")
            return False
    
    def extract_date_from_text(self, text):
        """Extract date in format DD/MM/YYYY HH:MM:SS from text"""
        import re
        # Pattern for DD/MM/YYYY HH:MM:SS format
        date_pattern = r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}'
        match = re.search(date_pattern, text)
        return match.group() if match else None
    
    def check_for_citacao_in_expedientes(self):
        """Check if 'Citação' appears in the Expedientes - inside the nested iframe"""
        try:
            print("🔍 Checking for 'Citação' in Expedientes...")
            
            # Switch to the expediente frame (this handles both ngFrame and nested iframe)
            if not self.switch_to_expediente_frame():
                print("❌ Could not switch to expediente frame, trying ngFrame only...")
                # Fallback to old behavior
                if not self.switch_to_ng_frame():
                    return False, None
            
            # Wait for content to load
            time.sleep(3)
            
            # The specific element where Citação appears
            # The ID pattern is processoParteExpedienteMenuGridList:X:j_idXXX:infoPPE
            # where X can be any number
            citacao_selectors = [
                # Exact ID from your example
                (By.XPATH, "//*[@id='processoParteExpedienteMenuGridList:0:j_id540:infoPPE']"),
                # Pattern matching for similar IDs (the j_id number might change)
                (By.XPATH, "//*[contains(@id, 'processoParteExpedienteMenuGridList') and contains(@id, 'infoPPE')]"),
                # More general pattern
                (By.XPATH, "//*[contains(@id, 'infoPPE')]"),
                # CSS selector versions
                (By.CSS_SELECTOR, "[id*='processoParteExpedienteMenuGridList'][id*='infoPPE']"),
                (By.CSS_SELECTOR, "[id*='infoPPE']"),
            ]
            
            found_citacao = False
            date_evento = None
            
            for selector_type, selector_value in citacao_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector_value)
                    if elements:
                        print(f"✅ Found {len(elements)} expediente info element(s)")
                        
                        # Check each element for Citação
                        for idx, element in enumerate(elements):
                            try:
                                element_text = element.text
                                if element_text:
                                    print(f"  Element {idx}: {element_text[:100]}...")
                                    
                                    # Check for Citação (case-insensitive)
                                    if "CITAÇÃO" in element_text.upper() or "CITACAO" in element_text.upper():
                                        print(f"✅ Found 'Citação' in element {idx}")
                                        
                                        # Extract date from the text
                                        date_evento = self.extract_date_from_text(element_text)
                                        if date_evento:
                                            print(f"📅 Found date in citação: {date_evento}")
                                        
                                        # Check if it's the Mandado - Citação pattern
                                        if "Mandado" in element_text and "Citação" in element_text:
                                            print(f"✅ Found 'Mandado - Citação' pattern")
                                        
                                        found_citacao = True
                                        return True, date_evento
                            except Exception as e:
                                print(f"⚠️ Error reading element {idx}: {str(e)}")
                                continue
                        
                        # If we found elements but no Citação
                        if not found_citacao:
                            print("❌ Found expediente elements but no 'Citação'")
                            
                        # Stop searching if we found the elements (even without Citação)
                        break
                        
                except Exception as e:
                    continue
            
            if not found_citacao:
                # Fallback: search the entire page for Citação
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text
                    if "CITAÇÃO" in body_text.upper() or "CITACAO" in body_text.upper():
                        print("✅ Found 'Citação' in page content (fallback method)")
                        # Try to extract date from the entire body text as fallback
                        date_evento = self.extract_date_from_text(body_text)
                        return True, date_evento
                    else:
                        print("❌ 'Citação' not found in page")
                        return False, None
                except:
                    print("❌ Could not search page content")
                    return False, None
            
            return found_citacao, None
            
        except Exception as e:
            print(f"❌ Error checking for Citação: {str(e)}")
            return False, None
    
    def close_process_tab(self):
        """Close the current process tab and return to main window"""
        try:
            # First switch back to default content (out of all iframes)
            self.reset_to_main_content()
            
            current_windows = self.driver.window_handles
            if len(current_windows) > 1:
                print("🔚 Closing process tab...")
                self.driver.close()
                self.driver.switch_to.window(self.original_window)
                time.sleep(1)
                return True
            return False
        except Exception as e:
            print(f"⚠️ Error closing tab: {str(e)}")
            try:
                self.driver.switch_to.window(self.original_window)
            except:
                pass
            return False
        """Click on a specific process element"""
        try:
            process_text = process_dict["text"]
            print(f"🎯 Opening process: {process_text}")
            
            # Store current windows
            windows_before = len(self.driver.window_handles)
            
            # Try to click the element
            element = process_dict["element"]
            
            # Scroll to element
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(1)
            
            # Try to click
            clicked = False
            try:
                element.click()
                clicked = True
                print(f"✅ Clicked on process: {process_text}")
            except:
                try:
                    self.driver.execute_script("arguments[0].click();", element)
                    clicked = True
                    print(f"✅ Clicked on process (JavaScript): {process_text}")
                except Exception as e:
                    print(f"❌ Failed to click process: {str(e)}")
                    return False
            
            if not clicked:
                return False
            
            # Wait for page to load
            time.sleep(5)
            
            # Check if new tab opened
            windows_after = len(self.driver.window_handles)
            if windows_after > windows_before:
                print("🆕 New tab opened, switching...")
                new_window = [w for w in self.driver.window_handles if w != self.original_window][-1]
                self.driver.switch_to.window(new_window)
                time.sleep(3)
            
            return True
            
        except Exception as e:
            print(f"❌ Error clicking process: {str(e)}")
            return False
    
    def wait_for_angular_load(self, timeout=15):
        """Wait for Angular application to fully load"""
        try:
            print("⏳ Waiting for Angular to load...")
            
            # Wait for Angular to be defined
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return typeof angular !== 'undefined' || typeof ng !== 'undefined'")
            )
            
            # Wait for any pending HTTP requests to complete
            script = """
            try {
                if (window.angular) {
                    var el = document.querySelector('[ng-app], [data-ng-app], .ng-scope');
                    if (el) {
                        var injector = angular.element(el).injector();
                        if (injector) {
                            var $http = injector.get('$http');
                            return $http.pendingRequests.length === 0;
                        }
                    }
                }
                // For Angular 2+
                if (window.getAllAngularTestabilities) {
                    return window.getAllAngularTestabilities().findIndex(x => !x.isStable()) === -1;
                }
                // Default to true if we can't detect Angular state
                return true;
            } catch(err) {
                return true;
            }
            """
            
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script(script)
            )
            print("✅ Angular loaded")
            return True
            
        except Exception as e:
            print(f"⚠️ Angular load wait timeout: {str(e)}")
            return False
    
    def click_expedientes_icon(self):
        """Click on the Expedientes icon to show expedientes content - NEW ANGULAR VERSION"""
        try:
            print("✉️ Looking for Expedientes icon to click...")
            
            # Wait for Angular to load first
            self.wait_for_angular_load()
            
            # Additional wait for the page to stabilize
            time.sleep(3)
            
            # Wait for the toolbar to be present with a longer timeout
            toolbar_found = False
            try:
                # Try multiple selectors for the toolbar
                toolbar_selectors = [
                    (By.TAG_NAME, "toolbar-processo"),
                    (By.CSS_SELECTOR, "toolbar-processo"),
                    (By.XPATH, "//toolbar-processo"),
                    (By.CSS_SELECTOR, "[class*='toolbar']"),
                    (By.XPATH, "//*[contains(local-name(), 'toolbar')]")
                ]
                
                for selector_type, selector_value in toolbar_selectors:
                    try:
                        toolbar = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((selector_type, selector_value))
                        )
                        toolbar_found = True
                        print(f"✅ Toolbar found using {selector_type}")
                        break
                    except:
                        continue
                        
                if not toolbar_found:
                    print("⚠️ Toolbar not found, waiting longer...")
                    time.sleep(5)
            except:
                print("⚠️ Toolbar wait failed, continuing anyway...")
            
            # Try to find the expedientes icon with multiple strategies
            expedientes_icon = None
            
            # Strategy 1: Direct class-based search after waiting
            try:
                expedientes_icon = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".expedientes-identity"))
                )
                print("✅ Found Expedientes icon with class selector")
            except:
                pass
            
            if not expedientes_icon:
                # Strategy 2: JavaScript to wait and find the icon
                try:
                    script = """
                    return new Promise((resolve) => {
                        let attempts = 0;
                        const maxAttempts = 20;
                        
                        const checkForIcon = () => {
                            attempts++;
                            console.log('Attempt ' + attempts + ' to find expedientes icon');
                            
                            // Method 1: By class
                            let icon = document.querySelector('div.expedientes-identity');
                            if (icon) {
                                console.log('Found by class selector');
                                resolve(icon);
                                return;
                            }
                            
                            // Method 2: By position in icones-acao-processo
                            let container = document.querySelector('icones-acao-processo');
                            if (container) {
                                let icons = container.querySelectorAll('div.icone-container');
                                console.log('Found ' + icons.length + ' icons in container');
                                if (icons.length >= 4) {
                                    console.log('Returning 4th icon');
                                    resolve(icons[3]);
                                    return;
                                }
                            }
                            
                            // Method 3: By searching all divs
                            let allDivs = document.querySelectorAll('div.icone-container');
                            for (let div of allDivs) {
                                if (div.className && div.className.includes('expedientes')) {
                                    console.log('Found by expedientes in className');
                                    resolve(div);
                                    return;
                                }
                            }
                            
                            if (attempts < maxAttempts) {
                                setTimeout(checkForIcon, 500);
                            } else {
                                resolve(null);
                            }
                        };
                        
                        checkForIcon();
                    });
                    """
                    
                    # Execute with a timeout
                    self.driver.set_script_timeout(15)
                    expedientes_icon = self.driver.execute_async_script(script)
                    if expedientes_icon:
                        print("✅ Found Expedientes icon using async JavaScript")
                except Exception as e:
                    print(f"⚠️ Async JavaScript search error: {str(e)}")
            
            if not expedientes_icon:
                # Strategy 3: Look for any clickable element that might be the expedientes icon
                try:
                    # Sometimes the icon might be rendered differently
                    alternative_selectors = [
                        (By.XPATH, "//div[contains(@class, 'icone') and contains(@class, 'expediente')]"),
                        (By.XPATH, "//div[contains(@onclick, 'expediente')]"),
                        (By.XPATH, "//div[contains(@ng-click, 'expediente')]"),
                        (By.XPATH, "//button[contains(text(), 'Expediente')]"),
                        (By.XPATH, "//a[contains(text(), 'Expediente')]"),
                        (By.XPATH, "//span[contains(text(), 'Expediente')]//ancestor::div[contains(@class, 'icone')]"),
                        # Try by icon position (usually 4th in the row)
                        (By.CSS_SELECTOR, ".icones-acao-processo > div:nth-of-type(4)"),
                        (By.XPATH, "//div[@class='icones-acao-processo']/div[4]"),
                    ]
                    
                    for selector_type, selector_value in alternative_selectors:
                        try:
                            elements = self.driver.find_elements(selector_type, selector_value)
                            for element in elements:
                                if element.is_displayed() and element.is_enabled():
                                    expedientes_icon = element
                                    print(f"✅ Found icon using: {selector_value}")
                                    break
                            if expedientes_icon:
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"⚠️ Alternative selector search error: {str(e)}")
            
            if not expedientes_icon:
                print("❌ Could not find Expedientes icon after all attempts")
                
                # Debug: Try to understand what's on the page
                try:
                    # Check if we're in an iframe
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    print(f"📄 Found {len(iframes)} iframes on page")
                    
                    # Check for any icons at all
                    any_icons = self.driver.find_elements(By.CSS_SELECTOR, "div.icone-container")
                    print(f"📄 Found {len(any_icons)} icon containers total")
                    
                    # Log their classes for debugging
                    for i, icon in enumerate(any_icons[:5]):  # First 5 only
                        classes = icon.get_attribute("class")
                        print(f"  Icon {i}: {classes}")
                except:
                    pass
                    
                return False
            
            # Try to click the icon with multiple methods
            clicked = False
            
            # First scroll into view
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", expedientes_icon)
                time.sleep(1)
            except:
                pass
            
            # Method 1: JavaScript click
            try:
                self.driver.execute_script("arguments[0].click();", expedientes_icon)
                clicked = True
                print("✅ Clicked Expedientes icon (JavaScript)")
            except Exception as e:
                print(f"⚠️ JavaScript click failed: {str(e)}")
            
            # Method 2: Regular click
            if not clicked:
                try:
                    expedientes_icon.click()
                    clicked = True
                    print("✅ Clicked Expedientes icon (regular click)")
                except Exception as e:
                    print(f"⚠️ Regular click failed: {str(e)}")
            
            # Method 3: Actions click
            if not clicked:
                try:
                    actions = ActionChains(self.driver)
                    actions.move_to_element(expedientes_icon).pause(0.5).click().perform()
                    clicked = True
                    print("✅ Clicked Expedientes icon (Actions)")
                except Exception as e:
                    print(f"⚠️ Actions click failed: {str(e)}")
            
            if not clicked:
                print("❌ Could not click Expedientes icon with any method")
                return False
            
            # Wait for navigation
            time.sleep(5)
            
            # Verify navigation success
            current_url = self.driver.current_url
            if "expedientes" in current_url.lower() or "expediente" in current_url.lower():
                print("✅ Successfully navigated to Expedientes")
                return True
            
            # Check if content changed
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                if any(keyword in body_text for keyword in ["Citação", "Intimação", "Ato de comunicação", "Expediente"]):
                    print("✅ Found expedientes content in page")
                    return True
            except:
                pass
            
            print("⚠️ Navigation unclear, but proceeding...")
            return True
            
        except Exception as e:
            print(f"❌ Error in click_expedientes_icon: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        """Click on the Expedientes icon to show expedientes content - NEW ANGULAR VERSION"""
        try:
            print("✉️ Looking for Expedientes icon to click...")
            
            # Wait longer for Angular to fully render
            time.sleep(5)
            
            # First, wait for the toolbar to be present
            try:
                toolbar = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "toolbar-processo"))
                )
                print("✅ Toolbar found")
            except:
                print("⚠️ Toolbar not found, continuing anyway...")
            
            # Try multiple strategies to find the Expedientes icon
            expedientes_icon = None
            
            # Strategy 1: Wait for the specific element to be clickable
            try:
                expedientes_icon = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "div.expedientes-identity"))
                )
                print("✅ Found Expedientes icon with WebDriverWait")
            except:
                pass
            
            if not expedientes_icon:
                # Strategy 2: JavaScript to find all icon containers and filter
                try:
                    script = """
                    // Find all icon containers
                    var icons = document.querySelectorAll('div.icone-container');
                    console.log('Found ' + icons.length + ' icon containers');
                    
                    // Look for the one with expedientes-identity class
                    for (var i = 0; i < icons.length; i++) {
                        console.log('Icon ' + i + ' classes: ' + icons[i].className);
                        if (icons[i].classList.contains('expedientes-identity')) {
                            console.log('Found expedientes icon at index ' + i);
                            return icons[i];
                        }
                    }
                    
                    // Alternative: look by position (4th icon)
                    var iconesContainer = document.querySelector('div.icones-acao-processo');
                    if (iconesContainer) {
                        var divs = iconesContainer.querySelectorAll('div.icone-container');
                        if (divs.length >= 4) {
                            console.log('Returning 4th icon by position');
                            return divs[3]; // 0-indexed, so 4th is index 3
                        }
                    }
                    
                    return null;
                    """
                    expedientes_icon = self.driver.execute_script(script)
                    if expedientes_icon:
                        print("✅ Found Expedientes icon using JavaScript search")
                except Exception as e:
                    print(f"⚠️ JavaScript search error: {str(e)}")
            
            if not expedientes_icon:
                # Strategy 3: Try all possible selectors
                expedientes_selectors = [
                    (By.CSS_SELECTOR, "div.icone-container.expedientes-identity.acao-icone"),
                    (By.CSS_SELECTOR, "div.expedientes-identity"),
                    (By.XPATH, "//div[contains(@class, 'expedientes-identity')]"),
                    (By.XPATH, "//icones-acao-processo//div[contains(@class, 'expedientes-identity')]"),
                    (By.XPATH, "//div[@class='icones-acao-processo']/div[4]"),
                    (By.CSS_SELECTOR, "icones-acao-processo > div > div:nth-child(4)"),
                    (By.CSS_SELECTOR, ".icones-acao-processo > div:nth-child(4)"),
                ]
                
                for selector_type, selector_value in expedientes_selectors:
                    try:
                        elements = self.driver.find_elements(selector_type, selector_value)
                        for element in elements:
                            if element.is_displayed():
                                expedientes_icon = element
                                print(f"✅ Found Expedientes icon using {selector_type}: {selector_value}")
                                break
                        if expedientes_icon:
                            break
                    except:
                        continue
            
            if not expedientes_icon:
                # Last resort: Try to find by tooltip or title
                try:
                    script = """
                    var allDivs = document.querySelectorAll('div');
                    for (var i = 0; i < allDivs.length; i++) {
                        var title = allDivs[i].getAttribute('title') || '';
                        var tooltip = allDivs[i].getAttribute('data-original-title') || '';
                        if (title.toLowerCase().includes('expediente') || 
                            tooltip.toLowerCase().includes('expediente')) {
                            return allDivs[i];
                        }
                    }
                    return null;
                    """
                    expedientes_icon = self.driver.execute_script(script)
                    if expedientes_icon:
                        print("✅ Found Expedientes icon by title/tooltip")
                except:
                    pass
            
            if not expedientes_icon:
                print("❌ Could not find Expedientes icon after all attempts")
                # Log page source for debugging
                print("📄 Current URL:", self.driver.current_url)
                # Log if we can see the toolbar
                try:
                    toolbar_html = self.driver.find_element(By.TAG_NAME, "toolbar-processo").get_attribute("innerHTML")
                    print("🔍 Toolbar HTML length:", len(toolbar_html) if toolbar_html else 0)
                except:
                    print("⚠️ Could not get toolbar HTML")
                return False
            
            # Click the icon with multiple attempts
            clicked = False
            
            # Attempt 1: Regular click
            try:
                expedientes_icon.click()
                clicked = True
                print("✅ Clicked Expedientes icon (regular click)")
            except Exception as e:
                print(f"⚠️ Regular click failed: {str(e)}")
            
            # Attempt 2: JavaScript click
            if not clicked:
                try:
                    self.driver.execute_script("arguments[0].click();", expedientes_icon)
                    clicked = True
                    print("✅ Clicked Expedientes icon (JavaScript click)")
                except Exception as e:
                    print(f"⚠️ JavaScript click failed: {str(e)}")
            
            # Attempt 3: Actions click
            if not clicked:
                try:
                    actions = ActionChains(self.driver)
                    actions.move_to_element(expedientes_icon).click().perform()
                    clicked = True
                    print("✅ Clicked Expedientes icon (Actions click)")
                except Exception as e:
                    print(f"❌ Actions click failed: {str(e)}")
                    return False
            
            if not clicked:
                print("❌ Could not click Expedientes icon with any method")
                return False
            
            # Wait for navigation/content to load
            time.sleep(5)
            
            # Verify that expedientes content is now visible
            print("🔍 Verifying Expedientes content loaded...")
            
            # Check if URL changed
            current_url = self.driver.current_url
            if "expedientes" in current_url.lower():
                print("✅ Navigated to Expedientes page (URL changed)")
                return True
            
            # Check for expedientes content
            try:
                # Wait for any expedientes content to appear
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(@id, 'expediente') or contains(@id, 'Expediente')]"))
                )
                print("✅ Expedientes content detected")
                return True
            except:
                pass
            
            # Check if page content changed significantly
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                if "Ato de comunicação" in body_text or "Intimação" in body_text or "Citação" in body_text:
                    print("✅ Found expedientes-related content in page")
                    return True
            except:
                pass
            
            print("⚠️ Could not verify Expedientes content, but proceeding...")
            return True
            
        except Exception as e:
            print(f"❌ Error in click_expedientes_icon: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def check_for_citacao_in_expedientes(self):
        """Check if 'Citação' appears in the Expedientes table"""
        try:
            print("🔍 Checking for 'Citação' in Expedientes table...")
            
            # Wait for page to stabilize after clicking Expedientes
            time.sleep(4)
            
            # Now we need to find and switch to the NESTED iframe that contains the actual content
            try:
                print("🔄 Looking for nested iframe with Expedientes content...")
                
                # The nested iframe usually has the Expedientes content
                # It's loaded dynamically and contains the processoExpedienteTab parameter
                nested_iframe_selectors = [
                    (By.XPATH, "//iframe[contains(@src, 'processoExpedienteTab')]"),
                    (By.XPATH, "//iframe[contains(@src, 'listAutosDigitais.seam')]"),
                    (By.CSS_SELECTOR, "iframe.frame"),
                    (By.CSS_SELECTOR, "iframe[title='']"),
                    (By.TAG_NAME, "iframe"),  # Fallback to any iframe
                ]
                
                nested_iframe = None
                for selector_type, selector_value in nested_iframe_selectors:
                    try:
                        iframes = self.driver.find_elements(selector_type, selector_value)
                        print(f"  Checking {len(iframes)} iframe(s) with {selector_type}")
                        
                        for iframe in iframes:
                            if iframe.is_displayed():
                                # Check if this iframe has the right src
                                src = iframe.get_attribute("src") or ""
                                if "processoExpedienteTab" in src or "listAutosDigitais" in src:
                                    nested_iframe = iframe
                                    print(f"✅ Found nested iframe with Expedientes content (src contains key terms)")
                                    break
                                # If no specific src match, take the first visible iframe as fallback
                                elif not nested_iframe:
                                    nested_iframe = iframe
                        
                        if nested_iframe and ("processoExpedienteTab" in (nested_iframe.get_attribute("src") or "") or 
                                             "listAutosDigitais" in (nested_iframe.get_attribute("src") or "")):
                            break
                    except Exception as e:
                        print(f"⚠️ Error finding nested iframe with {selector_type}: {str(e)}")
                        continue
                
                if not nested_iframe:
                    print("⚠️ Could not find nested iframe with specific src, trying to find any visible iframe...")
                    # Last resort: find any iframe that's visible
                    all_iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in all_iframes:
                        if iframe.is_displayed():
                            nested_iframe = iframe
                            print("⚠️ Using first visible iframe as fallback")
                            break
                
                if nested_iframe:
                    # Switch to the nested iframe
                    self.driver.switch_to.frame(nested_iframe)
                    print("✅ Switched to nested iframe containing Expedientes data")
                    time.sleep(2)
                    
                    # Now look for the table and check for Citação
                    citacao_found = False
                    global_date_evento = None
                    
                    # Method 1: Look for the specific infoPPE elements that contain expediente info
                    # IMPORTANT: Only check the FIRST element (most recent expediente)
                    try:
                        info_elements = self.driver.find_elements(By.XPATH, "//*[contains(@id, 'infoPPE')]")
                        if info_elements:
                            print(f"✅ Found {len(info_elements)} expediente info elements")
                            
                            # Only check the FIRST element (most recent)
                            if len(info_elements) > 0:
                                try:
                                    first_element = info_elements[0]
                                    element_text = first_element.text
                                    if element_text:
                                        print(f"  First (most recent) element: {element_text[:150]}...")
                                        
                                        # Check for Citação (case-insensitive) in first element only
                                        if "CITAÇÃO" in element_text.upper() or "CITACAO" in element_text.upper():
                                            print(f"✅ Found 'CITAÇÃO' in first (most recent) expediente")
                                            
                                            # Extract date from this element
                                            global_date_evento = self.extract_date_from_text(element_text)
                                            
                                            # Check if it's the pattern from your example
                                            if "Mandado" in element_text and "Citação" in element_text:
                                                print(f"✅ Found 'Mandado - Citação' pattern")
                                            elif "Carta" in element_text and "Citação" in element_text:
                                                print(f"✅ Found 'Carta - Citação' pattern")
                                            
                                            citacao_found = True
                                        else:
                                            print(f"❌ No 'Citação' found in first (most recent) expediente")
                                            # Explicitly NOT checking other elements - only the first one matters
                                except Exception as e:
                                    print(f"⚠️ Error reading first element: {str(e)}")
                            else:
                                print("⚠️ No expediente elements found")
                    except Exception as e:
                        print(f"⚠️ Could not check infoPPE elements: {str(e)}")
                    
                    # Method 2: Check the first row of the main table if not found
                    if not citacao_found:
                        try:
                            # Look for the first table row
                            first_row_selectors = [
                                (By.CSS_SELECTOR, "tr.rich-table-firstrow"),
                                (By.XPATH, "//tr[contains(@class, 'rich-table-firstrow')]"),
                                (By.XPATH, "//tbody[@id='processoParteExpedienteMenuGridList:tb']//tr[1]"),
                                (By.XPATH, "//table[contains(@id, 'processoParteExpedienteMenuGridList')]//tbody//tr[1]"),
                            ]
                            
                            first_row = None
                            for selector_type, selector_value in first_row_selectors:
                                try:
                                    element = self.driver.find_element(selector_type, selector_value)
                                    if element.is_displayed():
                                        first_row = element
                                        print(f"✅ Found first row of table")
                                        break
                                except:
                                    continue
                            
                            if first_row:
                                row_text = first_row.text.upper()
                                print(f"📄 First row content: {row_text[:200]}...")
                                
                                if "CITAÇÃO" in row_text or "CITACAO" in row_text:
                                    print("✅ Found 'CITAÇÃO' in the first row!")
                                    citacao_found = True
                                    # Extract date from the first row text that contains citação
                                    global_date_evento = self.extract_date_from_text(first_row.text)
                        except Exception as e:
                            print(f"⚠️ Could not check first row specifically: {str(e)}")
                    
                    # REMOVED Method 3 and 4 - Only search in most recent expediente
                    # User specifically requested to search ONLY in the first/most recent element
                    
                    # Return to the parent frame (ngFrame)
                    self.driver.switch_to.parent_frame()
                    print("🔄 Returned to parent frame")
                    
                    # Ensure we're back to default content for proper tab handling
                    try:
                        self.driver.switch_to.default_content()
                        print("🔄 Returned to default content")
                    except:
                        pass
                    
                    if citacao_found:
                        print("✅ CITAÇÃO found in Expedientes")
                        # Use the date extracted from the specific elements or try to extract from the page content
                        if global_date_evento:
                            print(f"📅 Found date for citação: {global_date_evento}")
                            return True, global_date_evento
                        else:
                            try:
                                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                                date_evento = self.extract_date_from_text(page_text)
                                if date_evento:
                                    print(f"📅 Found date for citação: {date_evento}")
                                return True, date_evento
                            except:
                                return True, None
                    else:
                        print("❌ 'Citação' not found in Expedientes table")
                        return False, None
                        
                else:
                    print("❌ Could not find nested iframe with Expedientes content")
                    # Try to check if content is directly in current frame
                    try:
                        page_text = self.driver.find_element(By.TAG_NAME, "body").text.upper()
                        if "CITAÇÃO" in page_text or "CITACAO" in page_text:
                            print("⚠️ Found 'CITAÇÃO' in current frame (fallback)")
                            date_evento = self.extract_date_from_text(page_text)
                            if date_evento:
                                print(f"📅 Found date for citação: {date_evento}")
                            # Ensure we're back to default content
                            try:
                                self.driver.switch_to.default_content()
                            except:
                                pass
                            return True, date_evento
                    except:
                        pass
                    return False, None
                    
            except Exception as e:
                print(f"❌ Error accessing nested iframe: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # Always try to return to default content on error
                try:
                    self.driver.switch_to.default_content()
                    print("🔄 Returned to default content after error")
                except:
                    pass
                    
                return False, None
                
        except Exception as e:
            print(f"❌ Error checking for Citação: {str(e)}")
            import traceback
            traceback.print_exc()
            # Always try to return to default content on error
            try:
                self.driver.switch_to.default_content()
                print("🔄 Returned to default content after main error")
            except:
                pass
            return False, None
    
    def return_to_comarca_selection(self):
        """Return to the main comarca selection page"""
        try:
            print("🏠 Returning to comarca selection...")
            
            # Try to click on "ACERVO" link to go back to comarca selection
            acervo_selectors = [
                (By.XPATH, "//a[@title='Acervo' and contains(@href, 'acervo')]"),
                (By.XPATH, "//a[text()='ACERVO']"),
                (By.XPATH, "//a[contains(@href, 'acervo') and contains(@class, 'navbar')]"),
                (By.ID, "navbar:lnkAcervo"),
                (By.XPATH, "//a[@id='navbar:lnkAcervo']"),
            ]
            
            acervo_link = None
            for selector_type, selector_value in acervo_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector_value)
                    for element in elements:
                        if element.is_displayed():
                            acervo_link = element
                            print(f"✅ Found ACERVO link using {selector_type}")
                            break
                    if acervo_link:
                        break
                except:
                    continue
            
            if acervo_link:
                try:
                    acervo_link.click()
                    print("✅ Clicked on ACERVO link")
                    time.sleep(3)
                    return True
                except:
                    try:
                        self.driver.execute_script("arguments[0].click();", acervo_link)
                        print("✅ Clicked on ACERVO link (JS)")
                        time.sleep(3)
                        return True
                    except:
                        print("❌ Failed to click ACERVO link")
                        return False
            else:
                print("❌ Could not find ACERVO link")
                return False
            
        except Exception as e:
            print(f"❌ Error returning to comarca selection: {str(e)}")
            return False
    
    def close_process_tab(self):
        """Close the current process tab and return to main window"""
        try:
            current_windows = self.driver.window_handles
            if len(current_windows) > 1:
                print("🔚 Closing process tab...")
                self.driver.close()
                self.driver.switch_to.window(self.original_window)
                time.sleep(1)
                return True
            return False
        except Exception as e:
            print(f"⚠️ Error closing tab: {str(e)}")
            try:
                self.driver.switch_to.window(self.original_window)
            except:
                pass
            return False
    
    def safe_close_process_tab(self):
        """Safely close process tab with improved error handling for 403 and similar errors"""
        try:
            print("🔄 Safely closing process tab...")
            
            # First, try to reset to main content (out of iframes)
            try:
                self.driver.switch_to.default_content()
            except:
                pass
            
            current_windows = self.driver.window_handles
            
            # If there's only one window, we're already in the right place
            if len(current_windows) <= 1:
                print("✅ Already on main window")
                return True
            
            # Multiple windows exist - need to close current and go back to original
            try:
                # Store the current window handle
                current_window = self.driver.current_window_handle
                
                # If we're already on the original window, find the other window to close
                if current_window == self.original_window:
                    print("🔍 On main window, looking for other windows to close...")
                    for window in current_windows:
                        if window != self.original_window:
                            try:
                                self.driver.switch_to.window(window)
                                self.driver.close()
                                print(f"🔚 Closed window {window}")
                                break
                            except Exception as e:
                                print(f"⚠️ Could not close window {window}: {str(e)}")
                                continue
                    
                    # Switch back to original window
                    self.driver.switch_to.window(self.original_window)
                    print("✅ Returned to original window")
                else:
                    # We're on a different window, close it and go back to original
                    print("🔚 Closing current tab...")
                    self.driver.close()
                    self.driver.switch_to.window(self.original_window)
                    print("✅ Closed tab and returned to main window")
                
                time.sleep(1)
                return True
                
            except Exception as e:
                print(f"⚠️ Error during window management: {str(e)}")
                # Emergency fallback - try to get back to original window
                try:
                    remaining_windows = self.driver.window_handles
                    if self.original_window in remaining_windows:
                        self.driver.switch_to.window(self.original_window)
                        print("✅ Emergency fallback - returned to original window")
                        return True
                    elif remaining_windows:
                        # If original window is gone, switch to first available
                        self.driver.switch_to.window(remaining_windows[0])
                        self.original_window = remaining_windows[0]  # Update reference
                        print("⚠️ Original window lost, switched to first available window")
                        return True
                except Exception as fallback_error:
                    print(f"❌ Emergency fallback failed: {str(fallback_error)}")
                    return False
                
        except Exception as e:
            print(f"❌ Critical error in safe_close_process_tab: {str(e)}")
            # Last resort - try to continue with automation
            try:
                windows = self.driver.window_handles
                if windows:
                    self.driver.switch_to.window(windows[0])
                    print("🆘 Last resort - switched to first available window")
                return False
            except:
                print("💀 Complete browser failure")
                return False
    
    def go_to_next_page(self):
        """Navigate to the next page if available"""
        try:
            print("📄 Checking for next page availability...")
            
            # First check if we're already on the last page by looking for current page info
            try:
                # Look for page info like "Página 8 de 8" or similar
                page_info_selectors = [
                    (By.XPATH, "//span[contains(text(), 'de') and contains(text(), 'Página')]"),
                    (By.XPATH, "//td[contains(text(), 'de') and (contains(text(), 'Página') or contains(text(), 'página'))]"),
                    (By.XPATH, "//div[contains(text(), 'Página') and contains(text(), 'de')]"),
                ]
                
                for selector_type, selector_value in page_info_selectors:
                    try:
                        page_info_elements = self.driver.find_elements(selector_type, selector_value)
                        for page_info in page_info_elements:
                            if page_info.is_displayed():
                                text = page_info.text
                                # Check if current page equals total pages (like "Página 8 de 8")
                                match = re.search(r'(?:Página|página)\s+(\d+)\s+de\s+(\d+)', text)
                                if match:
                                    current = int(match.group(1))
                                    total = int(match.group(2))
                                    print(f"📊 Page info: {current} de {total}")
                                    if current >= total:
                                        print("📄 Already on last page - no more pages")
                                        return False
                                    break
                    except:
                        continue
            except:
                pass
            
            # Look for next page button with improved detection
            next_selectors = [
                # More specific selectors for next page
                (By.XPATH, "//td[@class=' rich-datascr-button' and contains(@onclick, 'fastforward') and not(contains(@class, 'rich-datascr-button-dis'))]"),
                (By.XPATH, "//td[contains(@class, 'rich-datascr-button') and contains(@onclick, 'fastforward') and not(contains(@class, 'dis'))]"),
                (By.XPATH, "//td[contains(@onclick, 'fastforward') and text()='»' and not(contains(@class, 'disabled'))]"),
                (By.XPATH, "//td[text()='»' and not(contains(@class, 'disabled')) and not(contains(@class, 'inactive'))]"),
                (By.XPATH, "//a[text()='»' and not(contains(@class, 'disabled'))]"),
                (By.XPATH, "//a[contains(text(), 'Próximo') and not(contains(@class, 'disabled'))]"),
                (By.XPATH, "//a[contains(@title, 'próxima') and not(contains(@class, 'disabled'))]"),
                (By.CSS_SELECTOR, "a.ui-paginator-next:not(.ui-state-disabled)"),
            ]
            
            next_button = None
            for selector_type, selector_value in next_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector_value)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            # Check multiple attributes for disabled state
                            classes = (element.get_attribute("class") or "").lower()
                            onclick = (element.get_attribute("onclick") or "").lower()
                            style = (element.get_attribute("style") or "").lower()
                            
                            # Skip if disabled in any way
                            if any(disabled_indicator in classes for disabled_indicator in ["disabled", "inactive", "dis"]):
                                continue
                            if "disabled" in onclick or "return false" in onclick:
                                continue
                            if "cursor: default" in style or "pointer-events: none" in style:
                                continue
                            
                            next_button = element
                            print(f"✅ Found enabled next page button using {selector_type}")
                            break
                    if next_button:
                        break
                except:
                    continue
            
            if next_button:
                print("📄 Going to next page...")
                if self.safe_click(next_button):
                    time.sleep(3)
                    print("✅ Successfully navigated to next page")
                    return True
                elif self.safe_click(next_button, use_js=True):
                    time.sleep(3)
                    print("✅ Successfully navigated to next page (JS)")
                    return True
                else:
                    print("❌ Failed to click next page button")
                    return False
            else:
                print("📄 No enabled next page button found - reached last page")
                return False
            
        except Exception as e:
            print(f"⚠️ Error in pagination: {str(e)}")
            return False
    
    def process_current_page(self, comarca_name, page_num):
        """Process all processes on the current page with the new workflow"""
        try:
            print(f"\n📄 Processing page {page_num}...")
            
            # Find all process links on this page with their info
            process_list = self.find_process_links_on_current_page()
            
            if not process_list:
                print(f"⚠️ No processes found on page {page_num}")
                return 0
            
            processed_count = 0
            
            # Process each process on this page
            for idx, process_dict in enumerate(process_list, 1):
                process_text = process_dict["text"]
                process_info = process_dict.get("info", {})
                
                print(f"\n🔄 Page {page_num} - Process {idx}/{len(process_list)}: {process_text}")
                
                # Check if archived BEFORE clicking
                if process_info and process_info.get("is_archived", False):
                    print(f"⏭️ Skipping process {process_text} - ARQUIVADO")
                    continue
                
                # Click on the process
                if not self.click_process_by_element(process_dict):
                    print(f"⚠️ Skipping process {process_text} - could not open")
                    # Ensure we're back on the main window after any failure
                    try:
                        current_windows = self.driver.window_handles
                        if len(current_windows) > 1:
                            # There are multiple windows, ensure we're on the main one
                            if self.driver.current_window_handle != self.original_window:
                                # If any extra windows exist, close them
                                for window in current_windows:
                                    if window != self.original_window:
                                        try:
                                            self.driver.switch_to.window(window)
                                            self.driver.close()
                                        except:
                                            pass
                                # Switch back to main window
                                self.driver.switch_to.window(self.original_window)
                                print("🔄 Cleaned up extra windows and returned to main window")
                    except Exception as cleanup_error:
                        print(f"⚠️ Minor cleanup error: {str(cleanup_error)}")
                    continue
                
                # Check for CAPTCHA after opening process
                self.check_for_captcha_and_pause()
                
                # Variable to track if we should process this
                should_process = True
                has_citacao = False
                
                # Try to click on Expedientes icon (NEW ANGULAR VERSION)
                if not self.click_expedientes_icon():
                    print(f"⚠️ Could not access Expedientes for process {process_text} - checking if error 403 or similar")
                    
                    # Check if it's an error page (403, etc.)
                    try:
                        page_text = self.driver.find_element(By.TAG_NAME, "body").text.upper()
                        if "403" in page_text or "FORBIDDEN" in page_text or "ACESSO NEGADO" in page_text or "ERROR" in page_text:
                            print(f"🚫 Error 403 or similar detected for process {process_text} - skipping to avoid session corruption")
                            should_process = False
                        else:
                            print(f"⚠️ Unknown issue accessing Expedientes for process {process_text}")
                            should_process = False
                    except Exception as e:
                        print(f"⚠️ Could not determine error type for process {process_text}: {str(e)}")
                        should_process = False
                else:
                    # Successfully accessed Expedientes, check for Citação
                    has_citacao, date_evento = self.check_for_citacao_in_expedientes()
                
                # Only process if we successfully accessed the process
                if should_process:
                    if has_citacao:
                        print(f"✅ Found CITAÇÃO in process {process_text}")
                        
                        # Add to report with detailed information
                        process_entry = {
                            "process_number": process_text,
                            "parties": process_info.get("parties", "") if process_info else "",
                            "court": process_info.get("court", "") if process_info else "",
                            "distributed": process_info.get("distributed", "") if process_info else "",
                            "last_movement": process_info.get("last_movement", "") if process_info else "",
                            "detection_method": "expedientes_check",
                            "date_evento": date_evento or ""
                        }
                        
                        self.report_data[comarca_name]["citacao_processes"].append(process_entry)
                        print(f"📝 Added process {process_text} to citação report")
                    else:
                        print(f"❌ No CITAÇÃO found in process {process_text}")
                    
                    # Count as processed
                    self.report_data[comarca_name]["processed"] += 1
                    processed_count += 1
                
                # Close the process tab and return to main window (always try to close)
                # Use safer tab closing method
                self.safe_close_process_tab()
                
                # Small delay between processes to avoid issues
                time.sleep(2)
            
            print(f"✅ Completed page {page_num}: Processed {processed_count} processes")
            return processed_count
            
        except Exception as e:
            print(f"❌ Error processing page {page_num}: {str(e)}")
            return 0
    
    def process_comarca_page_by_page(self, comarca_name):
        """Process all processes in a comarca page by page"""
        try:
            print(f"\n{'='*80}")
            print(f"📍 Processing Comarca: {comarca_name}")
            print(f"{'='*80}")
            
            # Initialize comarca in report
            self.report_data[comarca_name] = {
                "citacao_processes": [],
                "total_processes": 0,
                "processed": 0
            }
            
            # Click on the comarca
            if not self.click_comarca(comarca_name):
                print(f"⚠️ Skipping comarca {comarca_name} - could not click")
                self.update_live_report(comarca_name)
                return
            
            # Apply party filter using search
            if not self.search_party_in_comarca():
                print(f"⚠️ Could not apply party filter, will search all processes")
            else:
                # After applying the filter, make sure we're on the first page
                print("📄 Ensuring we're on the first page after applying filter...")
                self.go_to_first_page()
            
            page_num = 1
            total_found = 0
            max_pages = 20  # Safety limit
            seen_processes = set()  # Track processes we've already seen
            consecutive_empty_pages = 0  # Track empty pages
            
            # Process page by page
            while page_num <= max_pages:
                print(f"\n📄 Starting page {page_num}...")
                
                # Get process list for this page
                process_list = self.find_process_links_on_current_page()
                
                if not process_list:
                    consecutive_empty_pages += 1
                    print(f"⚠️ No processes found on page {page_num} (empty page #{consecutive_empty_pages})")
                    
                    # If we get 2 consecutive empty pages, we're probably done
                    if consecutive_empty_pages >= 2:
                        print(f"📊 Two consecutive empty pages - ending pagination")
                        break
                    
                    # If this is the first page and it's empty, no processes in this comarca
                    if page_num == 1:
                        print(f"ℹ️ No processes found in {comarca_name}")
                        break
                    
                    # Try next page anyway
                    if not self.go_to_next_page():
                        print(f"📊 No more pages available after empty page {page_num}")
                        break
                    
                    page_num += 1
                    continue
                
                # Reset empty page counter if we found processes
                consecutive_empty_pages = 0
                
                # Check for duplicate processes (pagination loop detection)
                current_page_processes = {proc["text"] for proc in process_list}
                if current_page_processes.issubset(seen_processes):
                    print(f"⚠️ All processes on page {page_num} have been seen before - pagination loop detected!")
                    print(f"🔄 Ending pagination to avoid infinite loop")
                    break
                
                # Add new processes to seen set
                seen_processes.update(current_page_processes)
                
                # Process current page
                processed_on_page = self.process_current_page(comarca_name, page_num)
                total_found += processed_on_page
                
                # Update the total count
                self.report_data[comarca_name]["total_processes"] = len(seen_processes)
                
                print(f"✅ Completed page {page_num}: Found {len(process_list)} processes, processed {processed_on_page}")
                
                # Try to go to next page
                if not self.go_to_next_page():
                    print(f"📊 No more pages available after page {page_num} - reached end")
                    break
                
                page_num += 1
                
                # Extra safety: if we've processed a lot of pages, double-check
                if page_num > 10:
                    print(f"⚠️ Processing many pages ({page_num}), checking if we should continue...")
                    time.sleep(1)  # Brief pause for observation
            
            print(f"\n✅ Completed processing comarca: {comarca_name}")
            print(f"📊 Total pages processed: {page_num - 1}")
            print(f"📊 Unique processes seen: {len(seen_processes)}")
            print(f"📊 Total processed: {self.report_data[comarca_name]['processed']} processes")
            print(f"📊 Processes with Citação: {len(self.report_data[comarca_name]['citacao_processes'])}")
            
            # Update live report
            self.update_live_report(comarca_name)
            
            # CRITICAL: Navigate back to comarca selection after finishing
            print(f"\n🔄 Returning to comarca selection for next comarca...")
            self.return_to_comarca_selection()
            
        except Exception as e:
            print(f"❌ Error processing comarca {comarca_name}: {str(e)}")
            self.update_live_report(comarca_name)
            # Try to return to comarca selection even if there was an error
            try:
                self.return_to_comarca_selection()
            except:
                pass
    
    def update_live_report(self, comarca_name=None):
        """Update the live report with current data"""
        try:
            print("📝 Updating live report...")
            
            # Generate report text
            report_lines = []
            party_label = self.party_filter or "TODAS AS PARTES"
            report_lines.append(f"RELATÓRIO DE PROCESSOS - TJES - CITAÇÃO - LIVE")
            report_lines.append("=" * 80)
            report_lines.append(f"Data/Hora da última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            report_lines.append(f"Filtro de Parte: {party_label}")
            if comarca_name:
                report_lines.append(f"Última comarca processada: {comarca_name}")
            report_lines.append("=" * 80)
            report_lines.append("")

            total_stats = {
                "total_comarcas": len(self.report_data),
                "total_processes": 0,
                "total_processed": 0,
                "total_citacao": 0
            }

            for comarca, comarca_data in self.report_data.items():
                report_lines.append(f"\n{'='*60}")
                report_lines.append(f"COMARCA: {comarca}")
                report_lines.append(f"{'='*60}")
                report_lines.append(f"Total de processos encontrados: {comarca_data['total_processes']}")
                report_lines.append(f"Processos processados: {comarca_data['processed']}")
                report_lines.append(f"Processos com Citação: {len(comarca_data['citacao_processes'])}")
                report_lines.append("")

                # Update total stats
                total_stats["total_processes"] += comarca_data["total_processes"]
                total_stats["total_processed"] += comarca_data["processed"]
                total_stats["total_citacao"] += len(comarca_data["citacao_processes"])

                # List processes with citação
                if comarca_data["citacao_processes"]:
                    report_lines.append("📌 Processos com Citação:")
                    for process in comarca_data["citacao_processes"]:
                        report_lines.append(f"\n  Processo: {process['process_number']}")
                        if process.get('parties'):
                            report_lines.append(f"    Partes: {process['parties']}")
                        if process.get('court'):
                            report_lines.append(f"    Vara: {process['court']}")
                        if process.get('distributed'):
                            report_lines.append(f"    {process['distributed']}")
                        if process.get('last_movement'):
                            report_lines.append(f"    {process['last_movement']}")
                        if process.get('date_evento'):
                            report_lines.append(f"    📅 Data do Evento: {process['date_evento']}")
                        if process.get('detection_method'):
                            report_lines.append(f"    Método de detecção: Expedientes")
                    report_lines.append("")

            # Add summary
            report_lines.append("\n" + "="*80)
            report_lines.append("RESUMO GERAL PARCIAL")
            report_lines.append("="*80)
            report_lines.append(f"Total de Comarcas processadas até agora: {total_stats['total_comarcas']}")
            report_lines.append(f"Total de processos encontrados: {total_stats['total_processes']}")
            report_lines.append(f"Total de processos analisados: {total_stats['total_processed']}")
            report_lines.append(f"Total de processos com Citação: {total_stats['total_citacao']}")
            
            # Save text report
            report_text = "\n".join(report_lines)
            with open(self.live_report_txt, 'w', encoding='utf-8') as f:
                f.write(report_text)
            
            # Save JSON report
            with open(self.live_report_json, 'w', encoding='utf-8') as f:
                json.dump(self.report_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Live report updated: {self.live_report_txt}")
            
        except Exception as e:
            print(f"❌ Error updating live report: {str(e)}")
    
    def generate_final_report(self):
        """Generate the final report"""
        try:
            print("\n" + "="*80)
            print("📊 GENERATING FINAL REPORT - TJES CITAÇÃO")
            print("="*80)
            
            report_lines = []
            party_label = self.party_filter or "TODAS AS PARTES"
            report_lines.append(f"RELATÓRIO FINAL DE PROCESSOS - TJES - CITAÇÃO")
            report_lines.append("=" * 80)
            report_lines.append(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            report_lines.append("Tribunal: TJES - Tribunal de Justiça do Espírito Santo")
            report_lines.append(f"Filtro de Parte: {party_label}")
            report_lines.append("Tipo de busca: Processos com Citação detectados em Expedientes")
            report_lines.append("="*80)
            report_lines.append("")

            total_stats = {
                "total_comarcas": len(self.report_data),
                "total_processes": 0,
                "total_processed": 0,
                "total_citacao": 0
            }

            for comarca_name, comarca_data in self.report_data.items():
                report_lines.append(f"\n{'='*60}")
                report_lines.append(f"COMARCA: {comarca_name}")
                report_lines.append(f"{'='*60}")
                report_lines.append(f"Processos encontrados: {comarca_data['total_processes']}")
                report_lines.append(f"Processos processados: {comarca_data['processed']}")
                report_lines.append(f"Processos com Citação: {len(comarca_data['citacao_processes'])}")
                report_lines.append("")

                # Update total stats
                total_stats["total_processes"] += comarca_data["total_processes"]
                total_stats["total_processed"] += comarca_data["processed"]
                total_stats["total_citacao"] += len(comarca_data["citacao_processes"])

                # List processes with citação
                if comarca_data["citacao_processes"]:
                    report_lines.append("📌 Processos com Citação:")
                    for process in comarca_data["citacao_processes"]:
                        report_lines.append(f"\n  Processo: {process['process_number']}")
                        if process.get('parties'):
                            report_lines.append(f"    Partes: {process['parties']}")
                        if process.get('court'):
                            report_lines.append(f"    Vara: {process['court']}")
                        if process.get('distributed'):
                            report_lines.append(f"    {process['distributed']}")
                        if process.get('last_movement'):
                            report_lines.append(f"    {process['last_movement']}")
                        if process.get('date_evento'):
                            report_lines.append(f"    📅 Data do Evento: {process['date_evento']}")
                        if process.get('detection_method'):
                            report_lines.append(f"    Método de detecção: Expedientes")
                    report_lines.append("")

            # Add summary
            report_lines.append("\n" + "="*80)
            report_lines.append("RESUMO GERAL FINAL")
            report_lines.append("="*80)
            report_lines.append(f"Total de Comarcas processadas: {total_stats['total_comarcas']}")
            report_lines.append(f"Total de processos encontrados: {total_stats['total_processes']}")
            report_lines.append(f"Total de processos processados: {total_stats['total_processed']}")
            report_lines.append(f"Total de processos com Citação: {total_stats['total_citacao']}")
            
            # Save final report
            report_text = "\n".join(report_lines)
            final_report_file = os.path.join(self.report_dir, f"relatorio_final_tjes_citacao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(final_report_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            
            # Also save final JSON
            final_json_file = os.path.join(self.report_dir, f"relatorio_final_tjes_citacao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(final_json_file, 'w', encoding='utf-8') as f:
                json.dump(self.report_data, f, ensure_ascii=False, indent=2)
            
            # Print report to console
            print(report_text)
            
            print(f"\n✅ Final report saved to: {final_report_file}")
            print(f"✅ Final JSON data saved to: {final_json_file}")
            
            return final_report_file
            
        except Exception as e:
            print(f"❌ Error generating final report: {str(e)}")
            return None
    
    def run_automation(self, comarcas_to_process=None):
        """Run the complete automation"""
        try:
            # Setup driver
            self.setup_driver()
            
            # Simplified login and navigation
            print("\n" + "="*50)
            print("STEP 1: MANUAL LOGIN AND NAVIGATION")
            print("="*50)
            
            if not self.simplified_login_and_navigate():
                print("❌ Failed to reach Acervo page")
                return False
            
            # Get comarca list
            print("\n" + "="*50)
            print("STEP 2: GET COMARCA LIST")
            print("="*50)
            
            all_comarcas = self.get_comarca_list()
            if not all_comarcas:
                print("❌ No comarcas found")
                return False
            
            # Determine which comarcas to process
            if comarcas_to_process:
                # Filter to only requested comarcas
                comarcas = [c for c in all_comarcas if c in comarcas_to_process]
                print(f"📋 Processing {len(comarcas)} specified comarca(s)")
            else:
                comarcas = all_comarcas
                print(f"📋 Processing all {len(comarcas)} comarca(s)")
            
            # Process each comarca
            print("\n" + "="*50)
            print("STEP 3: PROCESS COMARCAS")
            print("="*50)
            
            for idx, comarca in enumerate(comarcas, 1):
                print(f"\n{'='*80}")
                print(f"🔄 COMARCA {idx}/{len(comarcas)}: {comarca}")
                print(f"{'='*80}")
                
                # Process comarca with page-by-page approach
                self.process_comarca_page_by_page(comarca)
                
                # Small delay between comarcas
                if idx < len(comarcas):
                    print("\n⏳ Preparing for next comarca...")
                    time.sleep(3)
            
            # Generate final report
            print("\n" + "="*50)
            print("STEP 4: GENERATE FINAL REPORT")
            print("="*50)
            self.generate_final_report()
            
            print("\n✅ Automation completed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Critical error in automation: {str(e)}")
            return False
            
        finally:
            if self.driver:
                print("\n🔚 Keeping browser open for verification...")
                time.sleep(10)


def main():
    """Main function to run the TJES PJE automation - Citação version"""
    print("🤖 PJE-TJES Process Automation - CITAÇÃO SEARCH")
    print("=" * 80)
    print("This script will process comarcas and search for 'Citação' in Expedientes")
    print("=" * 80)
    print("Features:")
    print("✅ Optional party filter (or process all parties)")
    print("✅ Checks for 'Arquivado' BEFORE clicking processes")
    print("✅ Clicks on Expedientes icon to check for Citação")
    print("✅ Captures detailed process information")
    print("✅ Automatic pagination")
    print("✅ Page-by-page processing")
    print("✅ Live reports after each comarca")
    print("=" * 80)

    # Ask about party filter
    print("\n📋 Party Filter Configuration")
    print("1. Filter by specific party name")
    print("2. Process ALL parties (no filter)")
    choice = input("Enter choice (1 or 2): ").strip()

    party_filter = None
    if choice == "1":
        party_filter = input("Enter party name to filter (e.g., 'daycoval'): ").strip()
        if party_filter:
            print(f"✅ Will filter by: {party_filter}")
        else:
            print("⚠️ Empty name provided, will process ALL parties")
            party_filter = None
    else:
        print("✅ Will process ALL parties (no filter)")

    # Ask if user wants to process specific comarcas or all
    print("\n📋 Comarca Selection")
    print("1. Process ALL comarcas")
    print("2. Process specific comarcas")
    choice = input("Enter choice (1 or 2): ").strip()

    comarcas_to_process = None
    if choice == "2":
        print("\nEnter comarca names (one per line, press Enter twice when done):")
        comarcas_to_process = []
        while True:
            comarca = input().strip()
            if comarca == "":
                if comarcas_to_process:
                    break
                else:
                    print("⚠️ Enter at least one comarca name")
                    continue
            comarcas_to_process.append(comarca)
            print(f"✅ Added: {comarca}")

        print(f"\n📊 Will process {len(comarcas_to_process)} specific comarca(s)")
    else:
        print("\n📊 Will process ALL comarcas")

    # Create automation instance with configuration
    automation = PJEDaycovalAutomationESCitacao(party_filter=party_filter, headless=False)
    
    try:
        # Run the automation
        success = automation.run_automation(comarcas_to_process=comarcas_to_process)
        
        if success:
            print("\n" + "="*80)
            print("🎉 AUTOMATION COMPLETED SUCCESSFULLY!")
            print("="*80)
            print(f"📁 Reports saved in: {automation.report_dir}")
            print(f"📝 Live reports were updated after each comarca")
            print(f"📊 Final report has been generated")
        else:
            print("\n" + "="*80)
            print("❌ AUTOMATION FAILED")
            print("="*80)
            print("Check the live reports for partial results")
        
    except KeyboardInterrupt:
        print("\n⚠️ Automation interrupted by user")
        print("📝 Check live reports for partial results")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        print("📝 Check live reports for partial results")
    finally:
        if automation.driver:
            try:
                print("\n🔍 Browser will remain open for 15 seconds for verification...")
                time.sleep(15)
                print("🔚 Closing browser...")
                automation.driver.quit()
            except:
                pass
    
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
