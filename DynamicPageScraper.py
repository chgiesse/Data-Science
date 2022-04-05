from bs4 import BeautifulSoup
from helium import *
import pandas as pd
import numpy as np
import time
import re
import multiprocessing
import math
from requests_html import HTMLSession
from fuzzywuzzy import fuzz
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


class NorthDataScraper:

    def __init__(self, name, party_id, session):
        self.session = session
        self.id = party_id
        self.name = name
        self.base_url = "https://northdata.de/"
        self.url = self.get_url()
        self.page = self.get_page()

    def get_url(self):
        # session = HTMLSession()
        url = self.base_url + self.name
        result = self.session.get(url)

        page = BeautifulSoup(result.text, "html.parser")
        cs = page.find("title", text=re.compile("Suche nach"))
        cd = page.find("sup", {"class": "title"})

        if cs is None:
            time.sleep(2)
            print(self.name + " eindeutig")
            return url
        elif cd is not None:
            time.sleep(2)
            return None
        else:
            headers = page.find_all("a", {"class": "title"})

            akt = []

            for i, header in enumerate(headers):
                check = header.select("sup")
                if len(check) == 0:
                    akt.append(i)

            akt_headers = []

            for i in akt:
                href = headers[i].get("href")
                text = headers[i].text.replace("\n", "", ).replace("  ", "").split(",")

                akt_headers.append([text, href])
            try:
                if len(akt_headers[0]) == 1 or len(akt_headers[0][0]) == 3 or not akt_headers:
                    time.sleep(2)
                    print(self.name + " nicht gefunden")
                    return None
                else:
                    if len(akt_headers[0][0]) == 2:
                        # print(akt_headers[0][0])
                        first_res = akt_headers[0][0][0]
                        match = fuzz.token_set_ratio(self.name, first_res)

                        if match >= 99:
                            # print([self.name, first_res, match])
                            url = self.base_url[:-1] + akt_headers[0][1]
                            # print(url)
                            time.sleep(2)
                            print(self.name + " in der Suche gefunden")
                            return url
                        else:
                            print(self.name + " nicht gefunden")
                            return None

                    else:
                        # print(akt_headers[1][0])
                        second_res = akt_headers[1][0][0]
                        match = fuzz.token_set_ratio(self.name, second_res)

                        if match >= 99:
                            url = self.base_url[:-1] + akt_headers[1][1]
                            # print(url)
                            time.sleep(2)
                            print(self.name + " in der Suche gefunden")
                            return url
                        else:
                            print(self.name + " nicht gefunden")
                            return None
            except IndexError:
                return None

    def get_page(self):

        if self.url is None:
            return None
        else:
            browser = start_chrome(str(self.url), headless=True, options=options)
            time.sleep(2)
            page = BeautifulSoup(browser.page_source, "html.parser")

            net_head = page.find("h3", text=re.compile("Netzwerk"))

            # Seite lange genug laden lassen um alle Elemnte zu bekommen

            if net_head is None:
                time.sleep(2)
                return page
            else:
                try:
                    # print(self.name, net_head)
                    WebDriverWait(browser, 15).until(ec.presence_of_element_located((By.CLASS_NAME, "node")))
                    page = BeautifulSoup(browser.page_source, "html.parser")
                except TimeoutError:
                    print("Netzwerk scheint leer zu sein.")
                    pass
                finally:
                    time.sleep(2)
                    return page

    def company_name(self):
        comp_name_r = self.page.find("h3", text=re.compile("Name"))

        if comp_name_r is None:
            return self.name
        else:
            comp_name = comp_name_r.find_next_sibling("div").select_one(".content").get_text()

            # print("Name wurde gefunden")
            return comp_name

    def company_address(self):
        comp_address = self.page.find(attrs={"title": "Suche an dieser Adresse"})
        if comp_address is None:
            return ""
        else:
            comp_address = comp_address.get_text()
            comp_address = comp_address.split(",")

        # print("Adresse wurde gefunden")
        return comp_address

    def company_register(self):
        comp_reg_r = self.page.find("h3", text=re.compile("Register"))

        if comp_reg_r is None:
            pass
        else:
            comp_reg = comp_reg_r.find_next_sibling("div").get_text().replace("Ut",
                                                                              "").replace("\n",
                                                                                          "").replace(" ",
                                                                                                      "", 14)
            # print("Register wurde gefunden")
            return comp_reg

    def company_description(self):
        c_comp_desc = self.page.find("h3", text=re.compile("Gegenstand"))

        if c_comp_desc is None:
            # print("Keine Beschreibung vorhanden")
            return ""
        else:
            comp_desc = c_comp_desc.find_next_sibling("p").get_text()
            # print("Beschreibung wurde gefunden")
            return comp_desc

    def merge_gen_info(self):
        gen_info = pd.DataFrame(columns=["Name", "Straße", "Ort", "Register", "Beschreibung"], index=[self.id])

        adresse = self.company_address()
        if adresse == "":
            gen_info["Straße"] = ""
            gen_info["Ort"] = ""
        else:
            gen_info["Straße"] = adresse[0]
            gen_info["Ort"] = adresse[1]

        gen_info["Name"] = self.company_name()
        gen_info["Register"] = self.company_register()
        gen_info["Beschreibung"] = self.company_description()

        return gen_info

    @staticmethod
    def catch_cac_error(cac):
        if "Stand" in cac[-1]:
            cac = cac[:-1]
        if (len(cac) / 2).is_integer():
            pass
        else:
            for i, item in enumerate(list(cac)):
                if (i / 2).is_integer() and item[-1] != "€":
                    cac = np.insert(cac, i - 1, "Keine Angabe")
                    break
        return cac

    @staticmethod
    def currency_transformer(df):
        for i, val in enumerate(df.iloc[:, 0]):
            # Normale Werte
            if val[-1] == "0":
                val = val.replace(".", "")

            # Millionen -> wenn der Betrag einstellig ist
            if val[-3:] == "Mio" and val[1] == ",":
                val = val.replace("Mio", "0000").replace(",", "")

            # Millionen -> wenn der Betrag zweistellig ist
            elif val[-3:] == "Mio" and val[1] != ",":
                val = val.replace("Mio", "00000").replace(",", "")

            # Milliarden -> wenn zweistellig Millionen
            elif val[-3:] == "Mrd" and val[0:3] == "0,0":
                val = val.replace("Mrd", "00000").replace(",", "")[2:]

                # Milliarden -> wenn dreistellig Millionen
            elif val[-3:] == "Mrd" and val[0] == "0" and val[1] == "," and val[2] != "0":
                val = val.replace("Mrd", "000000").replace(",", "")[1:]

            # Milliardern -> wenn einstellig
            elif val[-3:] == "Mrd" and val[0] != "0" and val[1] == ",":
                val = val.replace("Mrd", "0000000").replace(",", "")

            # Milliarden -> wenn zweistellig
            elif val[-3:] == "Mrd" and val[2] == "," and val[0] != "0":
                val = val.replace("Mrd", "00000000").replace(",", "")

            df.iloc[i, 0] = val
        return df

    def cac_transformer(self, stand_cac, aktiva, passiva, ausgaben):
        if (len(aktiva) / 2).is_integer():
            aktiva = pd.DataFrame(aktiva.reshape(int(len(aktiva) / 2), 2), columns=["Betrag", "Position"])
            if len(aktiva) != 0:
                aktiva["Betrag"] = aktiva["Betrag"].str.replace(" ", "").str[:-1]
                aktiva = self.currency_transformer(aktiva)
                aktiva["Typ"] = "Aktiva"
        else:
            aktiva = pd.DataFrame(aktiva[:-1].reshape(int(len(aktiva) / 2), 2), columns=["Betrag", "Position"])
            if len(aktiva) != 0:
                aktiva["Betrag"] = aktiva["Betrag"].str.replace(" ", "").str[:-1]
                aktiva = self.currency_transformer(aktiva)
                aktiva["Typ"] = "Aktiva"

        if (len(passiva) / 2).is_integer():
            passiva = pd.DataFrame(passiva.reshape(int(len(passiva) / 2), 2), columns=["Betrag", "Position"])
            if len(passiva) != 0:
                passiva["Betrag"] = passiva["Betrag"].str.replace(" ", "").str[:-1]
                passiva = self.currency_transformer(passiva)
                passiva["Typ"] = "Passiva"
        else:
            passiva = pd.DataFrame(passiva[:-1].reshape(int(len(passiva) / 2), 2), columns=["Betrag", "Position"])
            if len(passiva) != 0:
                passiva["Betrag"] = passiva["Betrag"].str.replace(" ", "").str[:-1]
                passiva = self.currency_transformer(passiva)
                passiva["Typ"] = "Passiva"

        if (len(ausgaben) / 2).is_integer():
            ausgaben = pd.DataFrame(ausgaben.reshape(int(len(ausgaben) / 2), 2), columns=["Betrag", "Position"])
            if len(ausgaben) != 0:
                ausgaben["Betrag"] = ausgaben["Betrag"].str.replace(" ", "").str[:-1]
                ausgaben = self.currency_transformer(ausgaben)
                ausgaben["Typ"] = "GuV"
        else:
            ausgaben = pd.DataFrame(ausgaben[:-1].reshape(int(len(ausgaben) / 2), 2), columns=["Betrag", "Position"])
            if len(ausgaben) != 0:
                ausgaben["Betrag"] = ausgaben["Betrag"].str.replace(" ", "").str[:-1]
                ausgaben = self.currency_transformer(ausgaben)
                ausgaben["Typ"] = "GuV"

        cac = pd.concat([aktiva, passiva, ausgaben])
        cac.insert(0, "Stand", stand_cac)
        cac.insert(0, "PARTY_ID", self.id)

        return cac

    def company_annual_accounts(self):
        c_cac = self.page.find("h3", text=re.compile("Jahresabschluss"))

        if c_cac is None:
            # print("Kein Jahresabschluss verfügbar")
            return None
        else:
            cac = c_cac.find_next_sibling("div", attrs={"class": "tab-content"})

            ausgaben = np.array([])
            aktiva = np.array([])
            passiva = np.array([])
            stand = self.page.find("span", attrs={"class": "legend3"}).text.split(" ")
            stand_cac = stand[1]

            for item in cac:
                part = item.find("div", {"class": "root"})
                # print(part.prettify())
                part_text = part.find_all(text=True)

                header_of_item = item.find("h4").text

                if header_of_item == "Ausgaben":
                    ausgaben = np.append(ausgaben, part_text)
                    ausgaben = self.catch_cac_error(ausgaben)
                elif header_of_item == "Aktiva":
                    aktiva = np.append(aktiva, part_text)
                    aktiva = self.catch_cac_error(aktiva)
                else:
                    passiva = np.append(passiva, part_text)
                    passiva = self.catch_cac_error(passiva)

            comp_cac = self.cac_transformer(stand_cac, aktiva, passiva, ausgaben)

            # print("Jahresabschluss wurde gefunden")
            return comp_cac

    def get_nodes(self):
        net_obj = self.page.find_all("a", {"class": "node"})

        if net_obj is None:
            # print("Kein Netzwerk vorhanden")
            return ""
        else:
            net_all = np.array([])

            for obj in net_obj:
                net_attrs = []

                obj_name = obj.text
                data_id = obj.get("data-id")
                data_href = obj.get("xlink:href")

                net_attrs.append([data_id, obj_name, data_href])

                net_all = np.append(net_all, net_attrs)

            net_objects = net_all.reshape(int(len(net_all) / 3), 3)
            net_objects_df = pd.DataFrame(net_objects, columns=["id", "Name", "Link to Northdata Webside"]).set_index(
                "id")
            # print("Knoten wurden gefunden")
            return net_objects_df

    def get_links(self):
        net_links = self.page.find_all("g", {"class": "link"})

        links_all = np.array([])

        for link in net_links:
            net_links = []

            target = link.get("data-target-id")
            source = link.get("data-source-id")

            net_links.append([source, target])

            links_all = np.append(links_all, net_links)

        all_links = links_all.reshape(int(len(links_all) / 2), 2)
        # print("Verbindungen wurden gefunden")
        return all_links

    def get_link_description(self):

        link_desc = np.array([])
        all_links = self.get_links()

        for i in range(0, len(all_links)):
            description = self.page.find("g", attrs={"data-source-id": str(all_links[i][0]),
                                                     "data-target-id": str(all_links[i][1])}).text

            link_desc = np.append(link_desc, description)

        link_desc = link_desc.reshape(len(link_desc), 1)
        # print("Verbindungsbeschreibungen wurde gefunden")
        return link_desc

    def comp_network(self):
        net_obj = self.get_nodes()
        all_links = self.get_links()

        network = pd.DataFrame(all_links)
        network[2] = self.get_link_description()
        network.columns = ["Source", "Target", "Description"]

        network_1 = network.join(net_obj["Name"], on="Source")

        network_2 = network_1.join(net_obj["Name"], on="Target", rsuffix="id")
        network_2.rename(columns={"Name": "Source Name",
                                  "Nameid": "Target Name"}, inplace=True)
        if len(network_2) != 0:
            network_2["Source Name"] = network_2["Source Name"].str[1:]
            network_2["Target Name"] = network_2["Target Name"].str[1:]
            network_2.insert(2, "PARTY_ID", int(self.id))
        else:
            pass

        # print("Netzwerke konnten zusammengeführt werden")

        return network_2.iloc[:, 2:]

    @staticmethod
    def catch_net_err(df):
        if df.shape[0] == 0:
            pass

        else:
            shape = (len(df) / 2)
            if df.iloc[0, 1] == "":
                if shape.is_integer():
                    for i in range(int(shape)):
                        df.iloc[int(i + shape), 1] = df.iloc[int(i + shape), 2]
                        df.iloc[int(i + shape), 2] = df.iloc[0, 2]

                    return df.iloc[int(shape):, :]

                else:
                    for i in range(len(df) - 1):
                        df.iloc[i + 1, 1] = df.iloc[i + 1, 2]
                        df.iloc[i + 1, 2] = df.iloc[0, 2]

                    return df.iloc[1:, :]

            else:
                return df


def scrape(name, party_id, session):
    scraper = NorthDataScraper(name, party_id, session)

    if scraper.page is None:
        pass
    else:
        try:
            gen_info = scraper.merge_gen_info()
            comp_cac = scraper.company_annual_accounts()
            comp_net = scraper.catch_net_err(scraper.comp_network())
            kill_browser()
            time.sleep(1.5)
            return gen_info, comp_cac, comp_net
        except ConnectionError:
            kill_browser()
            time.sleep(1.5)
            print("Keine Antwort vom Server")
            pass


def mp_worker(queue, names, party_ids):
    info_df = pd.DataFrame()
    cac_df = pd.DataFrame()
    net_df = pd.DataFrame()

    session = HTMLSession()

    for name, party_id in zip(names, party_ids):

        returns = scrape(name, party_id, session)

        if returns is None:
            pass
        else:
            info, cac, net = returns

            info_df = pd.concat([info_df, info], ignore_index=False)
            cac_df = pd.concat([cac_df, cac], ignore_index=True)
            net_df = pd.concat([net_df, net], ignore_index=True)

    queue.put([info_df, cac_df, net_df])


def mp_scraper(names, party_ids, processes):
    queue = multiprocessing.Queue()
    chunks = int(math.ceil(len(names) / processes))
    procs = []

    for i in range(processes):
        proc = multiprocessing.Process(target=mp_worker, args=(queue, names[chunks * i:chunks * (1 + i)],
                                                               party_ids[chunks * i:chunks * (1 + i)]
                                                               ))
        procs.append(proc)
        proc.start()

    results = []
    for i in range(processes):
        results.append(queue.get())

    for i in procs:
        i.join()

    return results


if __name__ == "__main__":

    start_time = time.time()
    res = mp_scraper(firmennamen, parties, 3)

    all_infos = pd.concat([res[0][0], res[1][0], res[2][0]], ignore_index=False)
    all_cacs = pd.concat([res[0][1], res[1][1], res[2][1]], ignore_index=True)
    all_nets = pd.concat([res[0][2], res[1][2], res[2][2]], ignore_index=True)

    all_infos.to_csv("General_information_1k.csv", sep=",")
    all_cacs.to_csv("Company_Annual_acounts_1k.csv", sep=",")
    all_nets.to_csv("Company_Networks_1k.csv", sep=",")

    runtime = time.time() - start_time
    print("---{} total runtime ---".format(runtime))
