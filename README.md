# Burgernet Alert Custom Integration for Home Assistant

A custom component that brings AMBER alerts and regional “Missing Child” notifications via the Burgernet Land Action Host API into Home Assistant. Polls every 10 min, filters by your location and exhibits one sensor with all relevant attributes.

---

## 📦 Installation

### 1. Via HACS (recommended)
1. Add this repo as **Custom Repository** in HACS:
   - **HACS → Integrations → ⋮ → Custom repositories**  
   - URL: `https://github.com/nnielzz/HA_Burgernet`  
   - Choose **Integration** and click **Add**.
2. In HACS, search for **Burgernet Alert** and click **Install**.
3. Restart Home Assistant.

### 2. Manually
1. Place the folder in your config folder: custom_components/burgernet-alert
