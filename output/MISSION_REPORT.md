# Drone Radiation Mission Safety Report

**Generated:** 2026-02-27 14:54:27
**Exposure Duration:** 50.4 min | **Total Data Points:** 8,398
**Platform:** CubePilot autopilot + Jetson Xavier NX (stationary)
**FLIGHT READINESS VERDICT:** ❌ GROUNDED — Do not fly until maintenance and decontamination check
**Score:** 45/100

---

## Executive Summary

A static radiation exposure test was conducted on a CubePilot and Jetson Xavier NX platform, subjecting the stationary system to a 50-minute active irradiation phase. While the hardware physically survived the maximum dose and maintained nominal telemetry without memory checksum errors, the system demonstrated critical logical instability. The operating system sustained 43 distinct integrity faults, and sensor streams recorded 158 extreme outliers exceeding 3-sigma thresholds. Furthermore, post-exposure diagnostics failed baseline recovery requirements due to excessive vibration noise and high compass variance, suggesting lingering sensor degradation. With a calculated safety score of 45/100, the aircraft is officially **GROUNDED**. Flight operations are prohibited until the platform undergoes comprehensive maintenance, sensor recalibration, and a verified decontamination check.

---

## Phase Statistics — PRE / DURING / POST

| Metric | PRE (Baseline) | DURING (Exposure) | POST (Recovery) |
|---|---|---|---|
| Vcc V | 5.1673 ± 0.0011 | 5.2601 ± 0.0038 | 5.2618 ± 0.0010 |
| Imu Temp C | 44.9925 ± 0.0350 | 45.0592 ± 0.7843 | 45.3154 ± 0.0199 |
| Baro Temp C | 47.7528 ± 0.0113 | 46.6426 ± 0.6869 | 47.0098 ± 0.0175 |
| Acc Mag | 987.8836 ± 0.1421 | 994.0001 ± 2.2927 | 992.4494 ± 0.1265 |
| Gyro Mag | 1.0620 ± 0.0807 | 1.8884 ± 0.8337 | 3.3430 ± 0.1111 |
| Mag Mag | 357.1598 ± 3.0374 | 271.9362 ± 21.3425 | 412.4026 ± 3.2249 |
| Vib Total | 0.1077 ± 0.0071 | 0.1841 ± 0.0385 | 0.1722 ± 0.0040 |
| Compass Variance | 0.0138 ± 0.0033 | 0.0194 ± 0.0061 | 0.0355 ± 0.0079 |
| Pos Horiz Variance | 0.0005 ± 0.0003 | 0.0008 ± 0.0010 | 0.0006 ± 0.0003 |
| Freemem | 65535.0000 ± 0.0000 | 65535.0000 ± 0.0000 | 65535.0000 ± 0.0000 |


---
## Sensor drift over elapsed time during radiation exposure sessions
![01_radiation_timeline.png](01_radiation_timeline.png)

**AI Commentary:** Graf zobrazuje časovú os kumulatívnej odchýlky (driftu) interných senzorov dronu – akcelerometra, gyroskopu a magnetometra – počas troch sekvenčných radiačných expozícií pri dávkovom príkone 3 Sv/h. Zatiaľ čo prvý beh (červená) vykazuje najprudší nárast počiatočnej degradácie, najmä pri gyroskope (~2 mrad/s) a magnetometri, druhý beh (oranžová) indikuje trvalé poškodenie senzorov s posunom kalibračného bodu bez známok zotavenia. Kritickou anomáliou je predčasné ukončenie tretieho behu (žltá) už po približne 9 minútach, čo nespĺňa povinný 30-minútový expozičný protokol a signalizuje úplný pád systému korelovaný s vysokým počtom chýb na zbernici I2C (18) a systémových zlyhaní (19). Tieto metriky potvrdzujú, že avionika prekročila limit celkovej ionizačnej dávky (TID), čo viedlo k fatálnej strate integrity dát a robí dron okamžite neschopným letu z dôvodu rizika nekontrolovateľného správania.

---
## Barometric temperature increase over elapsed time
![02_radiation_baro_temp.png](02_radiation_baro_temp.png)

**AI Commentary:** Graf znázorňuje časový vývoj vnútornej teploty barometrického senzora naprieč referenčným meraním, tromi expozičnými behmi a fázou obnovy. Zatiaľ čo prvý beh vykazuje počiatočný teplotný nábeh s následnou stabilizáciou a druhý beh udržiava konzistentný trend presahujúci 50 minút, tretí beh vykazuje kritickú anomáliu. Záznam tretieho expozičného cyklu (`04_DURING_exposure_run3`) sa náhle končí približne v 9. minúte, čím nespĺňa povinný 30-minútový interval a signalizuje predčasné zrútenie systému. Kombinácia tejto straty telemetrie s vysokým počtom chýb na zberniciach I2C (18) a PCIe (6) potvrdzuje, že kumulatívna dávka žiarenia spôsobila fatálne zlyhanie elektroniky, čím sa dron stáva okamžite neschopným letu.

---
## Navigation degradation heatmap — compass variance by session
![03_compass_variance_heatmap.png](03_compass_variance_heatmap.png)

**AI Commentary:** Graf zobrazuje časový vývoj rozptylu kompasu naprieč piatimi reláciami, čím vizualizuje degradáciu spoľahlivosti navigačných senzorov pod vplyvom dávkového príkonu 3 Sv/h. Kým prvé dva expozičné cykly vykazujú relatívnu stabilitu, kumulatívne radiačné poškodenie je evidentné v treťom cykle a následne v post-recovery fáze, kde rozptyl dosiahol kritické maximum 0,0734. Zásadnou anomáliou je predčasné ukončenie záznamu `04_DURING_exposure_run3` približne v 9. minúte, čo výrazne nedosahuje mandátny 30-minútový expozičný interval a indikuje tvrdý pád systému (system crash). Vzhľadom na tento výpadok a koreláciu s 18 chybami na zbernici I2C je navigačný hardvér považovaný za trvalo poškodený a dron za neschopný ďalšej bezpečnej letovej prevádzky (non-airworthy).

---
## 3D accelerometer state-space showing drift during exposure
![04_radiation_3d_map.png](04_radiation_3d_map.png)

**AI Commentary:** Graf vizualizuje 3D drift akcelerometra počas radiácie, pričom diagnostika odhalila kritickú nestabilitu potvrdzovanú 18 chybami I2C zbernice a 19 všeobecnými zlyhaniami systému. Keďže vizualizované dáta pokrývajú iba jednu neúplnú reláciu, nie je možné porovnať kumulatívne zhoršenie medzi jednotlivými behmi, ale rozptyl hodnôt naznačuje okamžitú stratu presnosti IMU. Záznam končí približne v 9. minúte, čo predstavuje závažnú anomáliu, keďže systém zlyhal hlboko pod hranicou povinného 30-minútového expozičného okna. Kombinácia vysokého počtu hardvérových chýb a predčasného pádu systému pri dávkovom príkone 3 Sv/h potvrdzuje okamžitú stratu letovej spôsobilosti a nízku mieru prežitia COTS elektroniky.

---
## Cumulative effects: temperature, vibration, compass over time
![05_cumulative_dose.png](05_cumulative_dose.png)

**AI Commentary:** Graf zobrazuje kumulatívne účinky žiarenia na hardvér dronu prostredníctvom metrík teploty barometra, celkových vibrácií a variancie kompasu počas troch sekvenčných expozícií pri dávkovom príkone 3 Sv/h. Zatiaľ čo prvá expozícia (červená) vykazuje najväčší počiatočný tepelný šok a vibračný nárast (až na 0,37 m/s²), druhá expozícia (oranžová) demonštruje pretrvávajúci zvýšený šum senzorov, hoci pri stabilnejších teplotách, čo naznačuje progresívnu degradáciu elektroniky. Kritická anomália nastala počas tretej expozície (žltá), ktorá bola predčasne ukončená už po približne 10 minútach, čím nespĺňa povinný 30-minútový protokol, čo pravdepodobne spôsobili nahromadené chyby (19 všeobecných zlyhaní a 18 chýb zbernice I2C). Tieto údaje potvrdzujú, že napriek akceptovateľnému driftu akcelerometra (3,33 mg) viedla kumulácia radiačného poškodenia a chýb zbernice ku katastrofickému zlyhaniu systému, čím sa dron stáva okamžite nespôsobilým na let a hardvér dosiahol hranicu svojej životnosti.

---
## Multi-panel telemetry: voltage, temp, free memory, load
![06_telemetry_overview.png](06_telemetry_overview.png)

**AI Commentary:** Tento grafický prehľad telemetrie zobrazuje vývoj napätia, teploty IMU, voľnej pamäte a systémovej záťaže počas základnej línie a troch po sebe idúcich radiačných expozícií. Zatiaľ čo prvé dva behy vykazujú relatívnu stabilitu senzorov, interné logy odhaľujú skrytú kumulatívnu degradáciu prostredníctvom 18 chýb zbernice I2C a 6 chýb PCIe, čo naznačuje poškodenie komunikačných rozhraní. Kritickou anomáliou je predčasné ukončenie záznamu `04_DURING_exposure_run3` (žltá čiara) už v 9. minúte, čím sa výrazne nesplnil povinný 30-minútový expozičný čas a indikuje to tvrdý pád systému spôsobený radiáciou. Kombinácia "zaseknutej" hodnoty pamäte na 65535 bajtoch a fatálneho zlyhania v treťom behu potvrdzuje, že elektronika utrpela nezvratné poškodenie a dron je okamžite nespôsobilý na ďalší let.

---
## Distribution histograms comparing PRE/DURING/POST phases
![07_dose_distribution.png](07_dose_distribution.png)

**AI Commentary:** Tu je technická analýza založená na poskytnutých dátach a kontexte:

Grafy znázorňujú hustotu distribúcie telemetrických dát pre fázy PRE (zelená), DURING (červená) a POST (modrá), pričom jasne vizualizujú vplyv radiácie 3 Sv/h na stabilitu senzorov a napájania. Fáza 'DURING' vykazuje výraznú bimodálnu distribúciu vibrácií a extrémny rozptyl variancie kompasu, čo indikuje progresívnu degradáciu odhadu stavu (EKF) a kumulatívne zhoršovanie presnosti MEMS senzorov v priebehu expozície. Kritickou anomáliou je extrémne nízky počet vzoriek vo fáze POST (n=75), čo v kombinácii s hlásenými 18 chybami I2C a 6 chybami PCIe naznačuje takmer okamžitý pád operačného systému alebo zamrznutie zbernice po ukončení ožarovania. Trvalý posun palubného napätia z nominálnych 5,17 V na 5,26 V a drift akcelerometra potvrdzujú poškodenie referenčných obvodov, čím sa dron stáva okamžite nespôsobilým na let (unairworthy) kvôli riziku nekontrolovateľného správania avioniky.

---
## Box-plot comparison of key metrics across phases
![08_phase_comparison_boxplot.png](08_phase_comparison_boxplot.png)

**AI Commentary:** Tu je technická analýza založená na poskytnutom grafe a údajoch:

(1) Tento súbor krabicových grafov (box-plots) porovnáva distribúciu kľúčových telemetrických metrík naprieč fázami pred (PRE), počas (DURING) a po (POST) expozícii, čím vizualizuje okamžitý a trvalý dopad ionizujúceho žiarenia s dávkovým príkonom 3 Sv/h na senzory dronu.
(2) Zatiaľ čo fáza "DURING" vykazuje extrémnu nestabilitu a masívny nárast odľahlých hodnôt (outliers) pri akcelerometri a napätí Vcc, fáza "POST" odhaľuje kumulatívnu degradáciu magnetometra, kde sa "Compass Variance" nevrátila na pôvodné hodnoty, ale zostala trvalo zvýšená, čo indikuje nezvratné poškodenie senzora.
(3) Kritickou anomáliou je statická hodnota voľnej pamäte (Freemem) na úrovni 65535 bajtov, čo signalizuje nasýtenie 16-bitového registra alebo zlyhanie logovania, pričom prítomnosť 18 chýb I2C a 6 chýb PCIe v OS Jetson potvrdzuje závažné narušenie komunikácie na hardvérových zberniciach.
(4) Vzhľadom na potvrdené hardvérové chyby (SEUs), nestabilitu napájania počas ožiarenia a trvalý drift navigačných senzorov v post-expozičnej fáze, je systém vyhodnotený ako nespôsobilý letu s vysokým rizikom straty kontroly.

---
## Numerical statistics table for all channels by phase
![09_stats_summary_card.png](09_stats_summary_card.png)

**AI Commentary:** Tento štatistický súhrn fáz kvantifikuje priemerné hodnoty a varianciu telemetrie pre základnú ("PRE"), expozičnú ("DURING") a zotavovaciu ("POST") fázu, čím priamo dokumentuje vplyv ionizujúceho žiarenia na avioniku. Porovnanie fáz odhaľuje počas ožiarenia masívnu degradáciu presnosti senzorov, kde štandardná odchýlka akcelerometra ("Acc Mag") vzrástla takmer 16-násobne a magnetometer vykázal kritický prepad intenzity poľa (z 357 na 271), čo indikuje silné radiačné rušenie alebo saturáciu senzorov. Medzi závažné anomálie patrí statická hodnota voľnej pamäte ("Freemem") na úrovni 65535, ktorá pravdepodobne indikuje pretečenie 16-bitového počítadla alebo zlyhanie reportovania, čo v kombinácii s 18 chybami I2C a 19 všeobecnými zlyhaniami na platforme Jetson potvrdzuje rozsiahlu korupciu dátových zberníc. Vzhľadom na zvýšenú varianciu kompasu a neistotu horizontálnej polohy je okamžitá letuschopnosť dronu kompromitovaná a hardvér vykazuje známky kumulatívneho poškodenia, ktoré by pri ďalšom ožiarení viedlo k fatálnemu zlyhaniu systému.

---
## Readiness gauge — score 45/100 — ❌ GROUNDED — Do not fly until maintenance and decontamination check
![10_flight_readiness_gauge.png](10_flight_readiness_gauge.png)

**AI Commentary:** Graf hodnotenia pripravenosti na let indikuje kritické zlyhanie so skóre 45/100, čo vedie k stavu „GROUNDED“ v dôsledku kumulatívnej degradácie elektroniky spôsobenej radiáciou. Hoci graf nezobrazuje časový priebeh jednotlivých expozičných cyklov, celkové poškodenie je evidentné v nulovom skóre integrity OS (0/20), spôsobenom 43 systémovými chybami (vrátane 18 chýb I2C a 6 chýb PCIe) a zaznamenaním 158 extrémnych odchýlok senzorov presahujúcich 3σ. Významné anomálie zahŕňajú kritickú odchýlku kompasu (156,3 %) a vysoký šum vibrácií, čo potvrdzuje, že ionizujúce žiarenie vážne narušilo interné komunikačné zbernice a spoľahlivosť fúzie senzorov. Vzhľadom na tieto fatálne chyby v integrite systému a avionike je dron okamžite neschopný letu a vyžaduje hĺbkovú hardvérovú diagnostiku na posúdenie trvalého poškodenia polovodičov.

---
## Jetson companion CPU/GPU temps and system power draw
![11_jetson_system_health.png](11_jetson_system_health.png)

**AI Commentary:** Graf zobrazuje telemetriu teploty CPU a spotreby energie (VDD IN) počítača Jetson Xavier NX počas troch ožarovacích behov, pričom sleduje vplyv ionizujúceho žiarenia na stabilitu hardvéru. Napriek tomu, že tepelné a výkonové profily zostávajú v normálnych medziach (30 – 32 °C), systém vykazuje vážnu nestabilitu potvrdenú vysokým počtom chýb na zberniciach I2C (18 chýb) a PCIe, čo naznačuje poškodenie komunikačných rozhraní žiarením. Kritickým zistením je, že ani jeden záznam nedosiahol požadovanú 30-minútovú expozíciu; beh č. 1 zlyhal katastrofálne už po cca 6 minútach, beh č. 3 po 9 minútach a najdlhší beh č. 2 sa predčasne ukončil na 23. minúte. Tieto opakované predčasné pády systému v kombinácii s degradáciou hardvérových rozhraní potvrdzujú, že palubný počítač nie je schopný prevádzky pri dávkovom príkone 3 Sv/h, čo okamžite vylučuje letovú spôsobilosť dronu pre autonómne misie.

---


## Flight Readiness Breakdown

| Criterion | Points | Max | Notes |
|---|---|---|---|
| Recovery Baseline | 10 | 30 | Vcc_V: 1.8% ✓; vib_total: 59.9% ✗; compass_variance: 156.3% ✗ |
| Max Dose Safe | 20 | 20 | No failures |
| No 3Sigma Spikes | 5 | 20 | 158 extreme outliers (>3σ) |
| Os Integrity | 0 | 20 | 43 OS-level faults logged |
| Telemetry Nominal | 10 | 10 | Nominal |
| **TOTAL** | **45** | **100** | **❌ GROUNDED — Do not fly until maintenance and decontamination check** |

