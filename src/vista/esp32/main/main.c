/**
 * VISTA ESP32-C3 Sentinel Firmware
 * =================================
 * Vehicle Intelligence & Safety Telematics Architecture (VISTA)
 *
 * Always-on vehicle sentinel: monitors PIR motion, battery voltage,
 * wakes the Raspberry Pi on intrusion, advertises alerts via BLE.
 *
 * Target:       ESP32-C3 (ESP-IDF v5.2+)
 * Deep sleep:   ~5 µA
 * Active power: ~30 mA (BLE advertising)
 *
 * Pin connections:
 *   GPIO0  ← PIR motion sensor   (HC-SR501, HIGH = motion)
 *   GPIO4  → Pi WAKE             (500 ms pulse to Pi GPIO5)
 *   GPIO6  ← Pi STATUS           (1 Hz heartbeat from Pi GPIO6)
 *   GPIO8  ← Battery divider     (ADC1_CH0, R1=100k / R2=33k)
 *
 * State machine:
 *   DEEP_SLEEP → wake every 1 s → check PIR & battery → decide next state
 *   ALERT      → wake Pi, BLE advertise, monitor Pi heartbeat
 *   LOW_BATT   → BLE warn, NEVER wake Pi, check voltage every 60 s
 *   NORMAL     → Pi is awake & driving, monitor heartbeat
 *
 * BLE GATT Service (UUID: 56495354-0001-1000-8000-00805F9B34FB):
 *   STATUS  (read / notify)  — battery_mv, mode, pir_triggered, pi_alive
 *   COMMAND (write)          — "arm" | "disarm"
 */

/* ── Includes ─────────────────────────────────────────────────────── */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <inttypes.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"

#include "esp_sleep.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_random.h"

#include "driver/gpio.h"

#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"

#include "nvs_flash.h"
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_gap_ble_api.h"
#include "esp_gatts_api.h"
#include "esp_bt_device.h"

/* ── Tag for ESP_LOGI / ESP_LOGE ─────────────────────────────────── */
static const char *TAG = "VISTA";

/* ═══════════════════════════════════════════════════════════════════
 *  PIN & HARDWARE DEFINITIONS
 * ═══════════════════════════════════════════════════════════════════ */

#define PIN_PIR             GPIO_NUM_0   /* PIR motion input           */
#define PIN_WAKE_PI         GPIO_NUM_4   /* Wake Pi (output)           */
#define PIN_PI_STATUS       GPIO_NUM_6   /* Pi heartbeat (input)       */

#define ADC_UNIT            ADC_UNIT_1
#define ADC_CHANNEL         ADC_CHANNEL_0 /* User: GPIO8 = ADC1_CH0   */
#define ADC_ATTEN           ADC_ATTEN_DB_11
#define ADC_BITWIDTH        ADC_BITWIDTH_12

/* Battery voltage divider: V_ADC = V_BAT × 33 / (100 + 33)           */
#define VOLTAGE_DIVIDER_NUMERATOR   133
#define VOLTAGE_DIVIDER_DENOMINATOR 33

/* ── Thresholds (millivolts) ─────────────────────────────────────── */
#define BATTERY_LOW_MV              11800   /* < this = low battery   */
#define BATTERY_RECOVER_MV          12000   /* > this = recovered     */

/* ═══════════════════════════════════════════════════════════════════
 *  TIMING CONSTANTS
 * ═══════════════════════════════════════════════════════════════════ */

#define DEEP_SLEEP_US               1000000 /* 1 s timer for PIR poll  */
#define PIR_CONFIRM_COUNT           3       /* samples to confirm      */
#define PIR_CONFIRM_INTERVAL_MS     100     /* between samples         */
#define WAKE_PI_PULSE_MS            500     /* Pi wake pulse width     */
#define ALERT_MONITOR_SECONDS       300     /* 5 min alert window      */
#define PI_ALIVE_TIMEOUT_SECONDS    60      /* Pi must boot within 60s */
#define PI_HEARTBEAT_TIMEOUT_SECONDS 30     /* no toggle = Pi dead     */
#define LOW_BATT_CHECK_SECONDS      60      /* re-check interval       */
#define LOW_BATT_STABLE_SECONDS     300     /* 5 min stable above 12V  */
#define POLL_INTERVAL_MS            100     /* main loop tick          */

/* ═══════════════════════════════════════════════════════════════════
 *  SYSTEM STATES
 * ═══════════════════════════════════════════════════════════════════ */

typedef enum {
    STATE_DEEP_SLEEP = 0,  /* Periodic PIR / battery polling           */
    STATE_ALERT      = 1,  /* Motion detected — wake Pi, BLE alert     */
    STATE_LOW_BATT   = 2,  /* Battery critically low                   */
    STATE_NORMAL     = 3,  /* Pi awake and driving                     */
} system_state_t;

/* ═══════════════════════════════════════════════════════════════════
 *  RTC DATA — survives deep-sleep reboots
 * ═══════════════════════════════════════════════════════════════════ */

RTC_DATA_ATTR system_state_t g_state = STATE_DEEP_SLEEP;
RTC_DATA_ATTR uint32_t       g_boot_count = 0;
RTC_DATA_ATTR uint32_t       g_alert_elapsed_s = 0;     /* seconds in ALERT       */
RTC_DATA_ATTR uint32_t       g_pi_dead_seconds = 0;     /* secs without heartbeat */
RTC_DATA_ATTR uint32_t       g_low_batt_stable_s = 0;   /* secs above recover V   */
RTC_DATA_ATTR uint32_t       g_deep_sleep_duration_s = 1; /* next sleep duration   */
RTC_DATA_ATTR bool           g_armed = true;             /* arm / disarm flag      */
RTC_DATA_ATTR bool           g_pi_was_alive = false;     /* Pi was seen alive      */

/* ── RTC snapshot of last-known readings ─────────────────────────── */
RTC_DATA_ATTR uint32_t g_last_battery_mv = 0;
RTC_DATA_ATTR bool     g_last_pir = false;

/* ═══════════════════════════════════════════════════════════════════
 *  BLE DEFINITIONS
 * ═══════════════════════════════════════════════════════════════════ */

/*
 * Custom 128-bit service UUID:  56495354-0001-1000-8000-00805F9B34FB
 * Stored in BLE little-endian byte order.
 */
static const uint8_t VISTA_SERVICE_UUID[16] = {
    0x56, 0x49, 0x53, 0x54,   /* time_low       "VIST" (LE)             */
    0x01, 0x00,               /* time_mid                                 */
    0x00, 0x10,               /* time_hi_and_version                      */
    0x80, 0x00,               /* clock_seq                                 */
    0x00, 0x80, 0x5F, 0x9B,  /* node[0..3]                               */
    0x34, 0xFB                /* node[4..5]                               */
};

#define GATTS_APP_ID            0
#define GATTS_SERVICE_HANDLE    0
#define GATTS_CHAR_STATUS_HANDLE  1
#define GATTS_CHAR_COMMAND_HANDLE 2

/* 16-bit characteristic UUIDs  (within the custom 128-bit service)   */
#define CHAR_UUID_STATUS        0xAA01
#define CHAR_UUID_COMMAND       0xAA02

#define STATUS_VALUE_MAX_LEN    64
#define COMMAND_VALUE_MAX_LEN   8

/* ── BLE state globals ───────────────────────────────────────────── */
static bool     g_ble_ready = false;
static bool     g_ble_connected = false;
static uint16_t g_conn_id = 0;
static esp_gatt_if_t g_gatts_if = ESP_GATT_IF_NONE;
static uint16_t g_service_handle = 0;
static uint16_t g_status_handle = 0;
static uint16_t g_command_handle = 0;
static bool     g_command_pending = false;
static char     g_command_buf[COMMAND_VALUE_MAX_LEN] = {0};

/* ── Forward declarations ─────────────────────────────────────────── */
static void ble_init(void);
static void ble_deinit(void);
static void ble_start_advertising(const char *name);
static void ble_stop_advertising(void);
static void ble_update_status(uint32_t batt_mv, system_state_t mode,
                              bool pir, bool pi_alive);

/* ═══════════════════════════════════════════════════════════════════
 *  ADC
 * ═══════════════════════════════════════════════════════════════════ */

static adc_oneshot_unit_handle_t g_adc_handle = NULL;
static adc_cali_handle_t         g_adc_cali   = NULL;

/**
 * Initialise ADC1_CH0 for battery voltage measurement.
 * Returns true on success.
 */
static bool adc_init(void)
{
    /* ── Oneshot unit ──────────────────────────────────────────── */
    adc_oneshot_unit_init_cfg_t unit_cfg = {
        .unit_id = ADC_UNIT,
        .clk_src = ADC_DIGI_CLK_SRC_DEFAULT,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    esp_err_t ret = adc_oneshot_new_unit(&unit_cfg, &g_adc_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "ADC unit init failed: %s", esp_err_to_name(ret));
        return false;
    }

    /* ── Channel config ────────────────────────────────────────── */
    adc_oneshot_chan_cfg_t chan_cfg = {
        .atten = ADC_ATTEN,
        .bitwidth = ADC_BITWIDTH,
    };
    ret = adc_oneshot_config_channel(g_adc_handle, ADC_CHANNEL, &chan_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "ADC channel config failed: %s", esp_err_to_name(ret));
        return false;
    }

    /* ── Calibration (curve-fitting for ESP32-C3) ──────────────── */
    adc_cali_curve_fitting_config_t cali_cfg = {
        .unit_id = ADC_UNIT,
        .chan = ADC_CHANNEL,
        .atten = ADC_ATTEN,
        .bitwidth = ADC_BITWIDTH,
    };
    ret = adc_cali_create_scheme_curve_fitting(&cali_cfg, &g_adc_cali);
    if (ret == ESP_OK) {
        ESP_LOGI(TAG, "ADC calibration enabled");
    } else {
        /* Calibration is optional — fall back to approximate conversion */
        ESP_LOGW(TAG, "ADC calibration unavailable (%s), using raw->mV approx",
                 esp_err_to_name(ret));
        g_adc_cali = NULL;
    }

    return true;
}

/**
 * Read battery voltage in millivolts.
 * Returns 0 on failure.
 */
static uint32_t read_battery_voltage(void)
{
    int raw = 0;
    esp_err_t ret = adc_oneshot_read(g_adc_handle, ADC_CHANNEL, &raw);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "ADC read failed: %s", esp_err_to_name(ret));
        return 0;
    }

    int adc_mv = 0;
    if (g_adc_cali) {
        ret = adc_cali_raw_to_voltage(g_adc_cali, raw, &adc_mv);
        if (ret != ESP_OK) {
            ESP_LOGW(TAG, "ADC cali convert failed, using raw");
            adc_mv = (int)((uint32_t)raw * 3100 / 4096);
        }
    } else {
        /* Approximate: 12-bit ADC, ~3100 mV full-scale at 11 dB   */
        adc_mv = (int)((uint32_t)raw * 3100 / 4096);
    }

    /* Scale back to battery voltage via divider ratio              */
    uint32_t batt_mv = (uint32_t)adc_mv * VOLTAGE_DIVIDER_NUMERATOR
                       / VOLTAGE_DIVIDER_DENOMINATOR;
    return batt_mv;
}

/* ═══════════════════════════════════════════════════════════════════
 *  GPIO
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * Configure all GPIOs.
 * Must be called on every cold/warm boot (GPIO state is lost in deep sleep
 * unless hold is enabled, but we reconfigure for simplicity).
 */
static void gpio_init_all(void)
{
    /* ── PIR input (GPIO0) ─────────────────────────────────────── */
    gpio_config_t pir_cfg = {
        .pin_bit_mask = (1ULL << PIN_PIR),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,  /* idle = LOW        */
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&pir_cfg);

    /* ── Pi WAKE output (GPIO4) ────────────────────────────────── */
    gpio_config_t wake_cfg = {
        .pin_bit_mask = (1ULL << PIN_WAKE_PI),
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,  /* default LOW       */
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&wake_cfg);
    gpio_set_level(PIN_WAKE_PI, 0);

    /* ── Pi STATUS input (GPIO6) ───────────────────────────────── */
    gpio_config_t status_cfg = {
        .pin_bit_mask = (1ULL << PIN_PI_STATUS),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,  /* idle = Pi off     */
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&status_cfg);
}

/**
 * Check PIR sensor (single read, no debounce).
 */
static inline bool check_pir(void)
{
    return gpio_get_level(PIN_PIR) == 1;
}

/**
 * Check PIR with software debounce: samples `count` times at `interval_ms`.
 * Returns true only if ALL samples are HIGH.
 */
static bool check_pir_confirmed(int count, int interval_ms)
{
    for (int i = 0; i < count; i++) {
        if (!check_pir()) {
            return false;
        }
        vTaskDelay(pdMS_TO_TICKS(interval_ms));
    }
    return true;
}

/**
 * Send a wake pulse to the Raspberry Pi.
 * Drives GPIO4 HIGH for `duration_ms`, then LOW.
 */
static void wake_pi(int duration_ms)
{
    ESP_LOGI(TAG, "Waking Pi — %d ms pulse on GPIO%d",
             duration_ms, PIN_WAKE_PI);
    gpio_set_level(PIN_WAKE_PI, 1);
    vTaskDelay(pdMS_TO_TICKS(duration_ms));
    gpio_set_level(PIN_WAKE_PI, 0);
}

/* ═══════════════════════════════════════════════════════════════════
 *  DEEP SLEEP
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * Enter deep sleep with timer-based wake.
 * Stores state in RTC memory before sleeping.
 */
static void enter_deep_sleep(uint32_t sleep_seconds,
                             system_state_t next_state)
{
    g_state = next_state;
    g_deep_sleep_duration_s = sleep_seconds;

    int64_t sleep_us = (int64_t)sleep_seconds * 1000000LL;
    esp_sleep_enable_timer_wakeup((uint64_t)sleep_us);

    ESP_LOGI(TAG, "Entering deep sleep for %" PRIu32 " s, state=%d",
             sleep_seconds, (int)next_state);

    /* Ensure WAKE pin is low before sleeping                       */
    gpio_set_level(PIN_WAKE_PI, 0);

    vTaskDelay(pdMS_TO_TICKS(50));  /* let UART flush               */
    esp_deep_sleep_start();
    /* ── never reaches here ──────────────────────────────────── */
}

/* ═══════════════════════════════════════════════════════════════════
 *  BLE CALLBACKS
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * GAP event handler: connection / disconnection.
 */
static void ble_gap_cb(esp_gap_ble_cb_event_t event,
                       esp_ble_gap_cb_param_t *param)
{
    switch (event) {
    case ESP_GAP_BLE_ADV_START_COMPLETE_EVT:
        ESP_LOGI(TAG, "BLE advertising started");
        break;

    case ESP_GAP_BLE_ADV_STOP_COMPLETE_EVT:
        ESP_LOGI(TAG, "BLE advertising stopped");
        break;

    case ESP_GAP_BLE_CONNECT_EVT:
        g_ble_connected = true;
        g_conn_id = param->connect.conn_id;
        ESP_LOGI(TAG, "BLE connected, conn_id=%d", g_conn_id);
        break;

    case ESP_GAP_BLE_DISCONNECT_EVT:
        g_ble_connected = false;
        g_conn_id = 0;
        ESP_LOGI(TAG, "BLE disconnected, reason=%d",
                 param->disconnect.reason);
        /* Re-start advertising so we're always discoverable         */
        ble_start_advertising(NULL);
        break;

    default:
        break;
    }
}

/**
 * GATT event handler: service registration, reads, writes.
 */
static void ble_gatts_cb(esp_gatts_cb_event_t event,
                         esp_gatt_if_t gatts_if,
                         esp_ble_gatts_cb_param_t *param)
{
    switch (event) {

    /* ── GATT interface registered ─────────────────────────────── */
    case ESP_GATTS_REG_EVT:
        g_gatts_if = gatts_if;
        ESP_LOGI(TAG, "GATT registered, gatts_if=%d", gatts_if);
        /* Now create the attribute table                           */
        ble_create_service(gatts_if);
        break;

    /* ── Attribute table created ───────────────────────────────── */
    case ESP_GATTS_CREATE_EVT: {
        g_service_handle = param->create.service_handle;
        /* Handles are sequential: service_handle+0..+5             */
        g_status_handle  = g_service_handle + 2;  /* STATUS value   */
        g_command_handle = g_service_handle + 5;  /* COMMAND value  */
        ESP_LOGI(TAG, "GATT table created: svc_h=%d, status_h=%d, cmd_h=%d",
                 g_service_handle, g_status_handle, g_command_handle);
        /* Start the service                                        */
        esp_ble_gatts_start_service(g_service_handle);
        break;
    }

    /* ── Service started ──────────────────────────────────────── */
    case ESP_GATTS_START_EVT:
        ESP_LOGI(TAG, "GATT service started, handle=%d",
                 param->start.service_handle);
        g_ble_ready = true;
        break;

    /* ── Client wrote a characteristic ─────────────────────────── */
    case ESP_GATTS_WRITE_EVT: {
        if (param->write.handle == g_command_handle) {
            size_t len = (param->write.len < COMMAND_VALUE_MAX_LEN)
                         ? param->write.len
                         : COMMAND_VALUE_MAX_LEN - 1;
            memcpy(g_command_buf, param->write.value, len);
            g_command_buf[len] = '\0';
            g_command_pending = true;
            ESP_LOGI(TAG, "BLE COMMAND: '%s'", g_command_buf);
        }
        break;
    }

    /* ── Client requested a read ──────────────────────────────── */
    case ESP_GATTS_READ_EVT:
        /* Handled via auto-response (set in attr table).           */
        break;

    /* ── Connection event from GATT perspective ────────────────── */
    case ESP_GATTS_CONNECT_EVT:
        ESP_LOGI(TAG, "GATT connected, conn_id=%d",
                 param->connect.conn_id);
        break;

    case ESP_GATTS_DISCONNECT_EVT:
        ESP_LOGI(TAG, "GATT disconnected, reason=%d",
                 param->disconnect.reason);
        break;

    default:
        break;
    }
}

/**
 * Build attribute table for the GATT service.
 */
static void ble_create_service(esp_gatt_if_t gatts_if)
{
    /* Define the 128-bit service UUID in esp_bt_uuid_t format.    */
    esp_bt_uuid_t svc_uuid = {
        .len = ESP_UUID_LEN_128,
    };
    memcpy(svc_uuid.uuid.uuid128, VISTA_SERVICE_UUID, 16);

    /* ── Service declaration ───────────────────────────────────── */
    esp_gatts_attr_db_t attr_db[8];  /* Service + 2 chars + descriptors */
    int idx = 0;

    /* Service declaration                                         */
    attr_db[idx].attr_control.auto_rsp = ESP_GATT_AUTO_RSP;
    attr_db[idx].att_desc = (esp_attr_desc_t){
        .uuid_length = ESP_UUID_LEN_16,
        .uuid_p      = (uint8_t[]){0x00, 0x28},  /* Primary Service */
        .perm        = ESP_GATT_PERM_READ,
        .max_length  = 16,
        .length      = 16,
        .value       = (uint8_t *)svc_uuid.uuid.uuid128,
    };
    idx++;

    /* ── STATUS characteristic ─────────────────────────────────── */
    esp_bt_uuid_t status_uuid = { .len = ESP_UUID_LEN_16 };
    status_uuid.uuid.uuid16 = CHAR_UUID_STATUS;

    /* Declaration */
    attr_db[idx].attr_control.auto_rsp = ESP_GATT_RSP_BY_APP;
    attr_db[idx].att_desc = (esp_attr_desc_t){
        .uuid_length = ESP_UUID_LEN_16,
        .uuid_p      = (uint8_t[]){0x03, 0x28},  /* Characteristic Decl */
        .perm        = ESP_GATT_PERM_READ,
        .max_length  = 5,
        .length      = 5,
        .value       = (uint8_t[]){
            ESP_GATT_CHAR_PROP_BIT_READ | ESP_GATT_CHAR_PROP_BIT_NOTIFY,
            0, 0,  /* handle placeholder */
            (uint8_t)(CHAR_UUID_STATUS & 0xFF),
            (uint8_t)((CHAR_UUID_STATUS >> 8) & 0xFF),
        },
    };
    idx++;

    /* Value */
    attr_db[idx].attr_control.auto_rsp = ESP_GATT_AUTO_RSP;
    attr_db[idx].att_desc = (esp_attr_desc_t){
        .uuid_length = ESP_UUID_LEN_16,
        .uuid_p      = (uint8_t[]){
            (uint8_t)(CHAR_UUID_STATUS & 0xFF),
            (uint8_t)((CHAR_UUID_STATUS >> 8) & 0xFF),
        },
        .perm        = ESP_GATT_PERM_READ,
        .max_length  = STATUS_VALUE_MAX_LEN,
        .length      = 0,
        .value       = NULL,
    };
    idx++;

    /* Client Characteristic Configuration Descriptor (for notify)  */
    attr_db[idx].attr_control.auto_rsp = ESP_GATT_AUTO_RSP;
    attr_db[idx].att_desc = (esp_attr_desc_t){
        .uuid_length = ESP_UUID_LEN_16,
        .uuid_p      = (uint8_t[]){0x02, 0x29},  /* CCCD */
        .perm        = ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE,
        .max_length  = 2,
        .length      = 2,
        .value       = (uint8_t[]){0x00, 0x00},
    };
    idx++;

    /* ── COMMAND characteristic ────────────────────────────────── */
    esp_bt_uuid_t cmd_uuid = { .len = ESP_UUID_LEN_16 };
    cmd_uuid.uuid.uuid16 = CHAR_UUID_COMMAND;

    /* Declaration */
    attr_db[idx].attr_control.auto_rsp = ESP_GATT_RSP_BY_APP;
    attr_db[idx].att_desc = (esp_attr_desc_t){
        .uuid_length = ESP_UUID_LEN_16,
        .uuid_p      = (uint8_t[]){0x03, 0x28},
        .perm        = ESP_GATT_PERM_READ,
        .max_length  = 5,
        .length      = 5,
        .value       = (uint8_t[]){
            ESP_GATT_CHAR_PROP_BIT_WRITE,
            0, 0,
            (uint8_t)(CHAR_UUID_COMMAND & 0xFF),
            (uint8_t)((CHAR_UUID_COMMAND >> 8) & 0xFF),
        },
    };
    idx++;

    /* Value */
    attr_db[idx].attr_control.auto_rsp = ESP_GATT_AUTO_RSP;
    attr_db[idx].att_desc = (esp_attr_desc_t){
        .uuid_length = ESP_UUID_LEN_16,
        .uuid_p      = (uint8_t[]){
            (uint8_t)(CHAR_UUID_COMMAND & 0xFF),
            (uint8_t)((CHAR_UUID_COMMAND >> 8) & 0xFF),
        },
        .perm        = ESP_GATT_PERM_WRITE,
        .max_length  = COMMAND_VALUE_MAX_LEN,
        .length      = 0,
        .value       = NULL,
    };
    idx++;

    /* ── Create the attribute table ─────────────────────────────── */
    esp_err_t ret = esp_ble_gatts_create_attr_tab(attr_db, gatts_if,
                                                  idx, GATTS_SERVICE_HANDLE);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create GATT attr table: %s",
                 esp_err_to_name(ret));
    }
}

/* ═══════════════════════════════════════════════════════════════════
 *  BLE CONTROL
 * ═══════════════════════════════════════════════════════════════════ */

static void ble_init(void)
{
    ESP_ERROR_CHECK(nvs_flash_init());

    /* Release classic BT memory (ESP32-C3 is BLE-only anyway)      */
    ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT));

    esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_bt_controller_init(&bt_cfg));
    ESP_ERROR_CHECK(esp_bt_controller_enable(ESP_BT_MODE_BLE));

    ESP_ERROR_CHECK(esp_bluedroid_init());
    ESP_ERROR_CHECK(esp_bluedroid_enable());

    ESP_ERROR_CHECK(esp_ble_gap_register_callback(ble_gap_cb));
    ESP_ERROR_CHECK(esp_ble_gatts_register_callback(ble_gatts_cb));

    /* Register the GATT application                               */
    ESP_ERROR_CHECK(esp_ble_gatts_app_register(GATTS_APP_ID));

    /* Wait until service creation completes (async)               */
    int timeout = 0;
    while (!g_ble_ready && timeout < 50) {
        vTaskDelay(pdMS_TO_TICKS(100));
        timeout++;
    }
    if (!g_ble_ready) {
        ESP_LOGE(TAG, "BLE init timed out waiting for GATT service");
    }
}

static void ble_deinit(void)
{
    ble_stop_advertising();
    g_ble_ready = false;
    g_ble_connected = false;
    esp_bluedroid_disable();
    esp_bluedroid_deinit();
    esp_bt_controller_disable();
    esp_bt_controller_deinit();
    ESP_LOGI(TAG, "BLE de-initialised");
}

/**
 * Start BLE advertising with optional device name override.
 * Pass NULL to keep the current name.
 */
static void ble_start_advertising(const char *name)
{
    /* ── Configure advertising data ───────────────────────────── */
    esp_ble_adv_data_t adv_data = {0};
    adv_data.set_scan_rsp        = false;
    adv_data.include_name        = (name != NULL);
    adv_data.include_txpower     = false;
    adv_data.flag                = (ESP_BLE_ADV_FLAG_GEN_DISC |
                                    ESP_BLE_ADV_FLAG_BREDR_NOT_SPT);

    if (name) {
        esp_ble_gap_set_device_name(name);
    }

    esp_ble_gap_config_adv_data(&adv_data);

    /* ── Advertising parameters ───────────────────────────────── */
    esp_ble_adv_params_t adv_params = {
        .adv_int_min        = 0x20,   /* 20 ms * 1.25 = 25 ms     */
        .adv_int_max        = 0x40,   /* 40 ms * 1.25 = 50 ms     */
        .adv_type           = ADV_TYPE_IND,
        .own_addr_type      = BLE_ADDR_TYPE_PUBLIC,
        .channel_map        = ADV_CHNL_ALL,
        .adv_filter_policy  = ADV_FILTER_ALLOW_SCAN_ANY_CON_ANY,
    };

    esp_ble_gap_start_advertising(&adv_params);
}

static void ble_stop_advertising(void)
{
    esp_ble_gap_stop_advertising();
}

/**
 * Build and send a STATUS update (read value + optional notification).
 */
static void ble_update_status(uint32_t batt_mv, system_state_t mode,
                              bool pir, bool pi_alive)
{
    if (!g_ble_ready) return;

    char buf[STATUS_VALUE_MAX_LEN];
    const char *mode_str = "?";
    switch (mode) {
    case STATE_DEEP_SLEEP: mode_str = "sleep";  break;
    case STATE_ALERT:      mode_str = "alert";  break;
    case STATE_LOW_BATT:   mode_str = "lowbatt"; break;
    case STATE_NORMAL:     mode_str = "normal"; break;
    }

    int len = snprintf(buf, sizeof(buf),
                       "bat:%" PRIu32 ";mode:%s;pir:%d;pi:%d;armed:%d",
                       batt_mv, mode_str, pir ? 1 : 0,
                       pi_alive ? 1 : 0, g_armed ? 1 : 0);

    /* Update the GATT database value so read requests return this  */
    if (g_status_handle > 0) {
        esp_ble_gatts_set_attr_value(g_status_handle, len,
                                     (uint8_t *)buf);
    }

    /* Send notification if connected                              */
    if (g_ble_connected && g_conn_id > 0 && g_status_handle > 0) {
        esp_ble_gatts_send_indicate(GATTS_APP_ID, g_conn_id,
                                     g_status_handle, len,
                                     (uint8_t *)buf, false);
    }
}

/**
 * Process a pending BLE COMMAND write.
 */
static void ble_process_command(void)
{
    if (!g_command_pending) return;
    g_command_pending = false;

    ESP_LOGI(TAG, "Processing BLE command: '%s'", g_command_buf);

    if (strcmp(g_command_buf, "arm") == 0) {
        g_armed = true;
        ESP_LOGI(TAG, "System ARMED");
    } else if (strcmp(g_command_buf, "disarm") == 0) {
        g_armed = false;
        ESP_LOGI(TAG, "System DISARMED");
    } else {
        ESP_LOGW(TAG, "Unknown BLE command: '%s'", g_command_buf);
    }
}

/* ═══════════════════════════════════════════════════════════════════
 *  STATE MACHINE — ACTIVE LOOP  (ALERT / NORMAL / LOW_BATT)
 * ═══════════════════════════════════════════════════════════════════ */

/**
 * Run the ALERT state: wake Pi, advertise BLE, monitor.
 * This function blocks until the state transitions.
 */
static void run_state_alert(void)
{
    ESP_LOGI(TAG, ">> STATE_ALERT");
    uint32_t start_s = (uint32_t)(esp_timer_get_time() / 1000000LL);

    /* ── Wake the Pi ──────────────────────────────────────────── */
    wake_pi(WAKE_PI_PULSE_MS);

    /* ── Start BLE advertising with alert name ────────────────── */
    ble_init();
    ble_start_advertising(BLE_ALERT_NAME);

    /* Send initial notification                                    */
    ble_update_status(g_last_battery_mv, STATE_ALERT,
                      g_last_pir, g_pi_was_alive);

    bool pi_alive = false;
    bool pi_timed_out = false;
    uint32_t pi_alive_since = 0;
    int prev_status = 0;
    uint32_t last_toggle_s = 0;
    uint32_t last_batt_check_s = 0;
    uint32_t last_status_update_s = 0;

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(POLL_INTERVAL_MS));

        uint32_t now_s = (uint32_t)(esp_timer_get_time() / 1000000LL);
        uint32_t elapsed = now_s - start_s;

        /* ── Check Pi heartbeat (GPIO6 toggling) ───────────────── */
        int curr_status = gpio_get_level(PIN_PI_STATUS);
        if (curr_status != prev_status) {
            last_toggle_s = now_s;
            prev_status = curr_status;
            if (!pi_alive) {
                pi_alive = true;
                pi_alive_since = now_s;
                g_pi_was_alive = true;
                ESP_LOGI(TAG, "Pi heartbeat detected (alive)");

                /* Transition to NORMAL state (Pi is driving)       */
                /* But we keep monitoring from here; the 5-min      */
                /* timer still runs.                                */
            }
        }

        /* ── Pi timeout check ──────────────────────────────────── */
        if (!pi_alive && elapsed > PI_ALIVE_TIMEOUT_SECONDS) {
            pi_timed_out = true;
            ESP_LOGW(TAG, "Pi did NOT respond within %d s",
                     PI_ALIVE_TIMEOUT_SECONDS);
            break;  /* Give up, go back to deep sleep              */
        }

        /* ── Check PIR periodically ────────────────────────────── */
        bool pir_now = check_pir();
        g_last_pir = pir_now;

        /* ── Battery check (every 5 s) ─────────────────────────── */
        if (now_s - last_batt_check_s >= 5) {
            g_last_battery_mv = read_battery_voltage();
            last_batt_check_s = now_s;
            if (g_last_battery_mv > 0 && g_last_battery_mv < BATTERY_LOW_MV) {
                ESP_LOGW(TAG, "Battery critical during alert (%" PRIu32 " mV)",
                         g_last_battery_mv);
                ble_deinit();
                enter_deep_sleep(LOW_BATT_CHECK_SECONDS, STATE_LOW_BATT);
                return;
            }
        }

        /* ── Process BLE commands ──────────────────────────────── */
        ble_process_command();

        /* ── Update BLE status (every 2 s) ─────────────────────── */
        if (now_s - last_status_update_s >= 2) {
            ble_update_status(g_last_battery_mv, STATE_ALERT,
                              g_last_pir, pi_alive);
            last_status_update_s = now_s;
        }

        /* ── Exit conditions ───────────────────────────────────── */
        /* 1. Pi alive for 5 minutes AND no recent motion → sleep   */
        if (pi_alive && !g_last_pir &&
            (now_s - pi_alive_since) >= ALERT_MONITOR_SECONDS) {
            ESP_LOGI(TAG, "Pi alive for %d s, no motion — returning to sleep",
                     ALERT_MONITOR_SECONDS);
            break;
        }

        /* 2. Not armed → sleep                                     */
        if (!g_armed) {
            ESP_LOGI(TAG, "System disarmed — returning to sleep");
            break;
        }

        /* Safety: if somehow in alert > 15 min, abort              */
        if (elapsed > 900) {
            ESP_LOGW(TAG, "Alert timeout (15 min) — returning to sleep");
            break;
        }
    }

    /* ── Cleanup BLE before sleeping ───────────────────────────── */
    ble_deinit();
    g_alert_elapsed_s = 0;
    g_pi_dead_seconds = 0;

    if (!pi_alive && !pi_timed_out) {
        /* Pi was alive at some point but we're exiting             */
    }

    enter_deep_sleep(1, STATE_DEEP_SLEEP);
}

/**
 * Run the LOW_BATT state: advertise warning, NEVER wake Pi.
 */
static void run_state_low_batt(void)
{
    ESP_LOGI(TAG, ">> STATE_LOW_BATT");

    /* Quick BLE burst to announce low battery                      */
    ble_init();
    ble_start_advertising(BLE_LOWBATT_NAME);

    uint32_t batt_mv = read_battery_voltage();
    g_last_battery_mv = batt_mv;
    ESP_LOGW(TAG, "Battery LOW: %" PRIu32 " mV (threshold %d mV)",
             batt_mv, BATTERY_LOW_MV);

    /* Build a name with actual voltage for the advertisement      */
    char name_buf[32];
    snprintf(name_buf, sizeof(name_buf), "VISTA-LOW-BATT-%" PRIu32 "mV",
             batt_mv);
    esp_ble_gap_set_device_name(name_buf);
    ble_update_status(batt_mv, STATE_LOW_BATT, false, false);

    /* Advertise for ~10 seconds then go back to sleep             */
    for (int i = 0; i < 10; i++) {
        ble_process_command();
        vTaskDelay(pdMS_TO_TICKS(1000));

        /* Re-check battery during advertising                     */
        if (i == 5) {
            batt_mv = read_battery_voltage();
            g_last_battery_mv = batt_mv;
            if (batt_mv >= BATTERY_RECOVER_MV) {
                g_low_batt_stable_s += 5;
            } else {
                g_low_batt_stable_s = 0;
            }
        }
    }

    ble_deinit();

    /* ── Check recovery condition ───────────────────────────────── */
    batt_mv = read_battery_voltage();
    g_last_battery_mv = batt_mv;

    if (batt_mv >= BATTERY_RECOVER_MV) {
        g_low_batt_stable_s += LOW_BATT_CHECK_SECONDS;
        ESP_LOGI(TAG, "Battery recovering: %" PRIu32 " mV, stable for %" PRIu32 " s",
                 batt_mv, g_low_batt_stable_s);

        if (g_low_batt_stable_s >= LOW_BATT_STABLE_SECONDS) {
            ESP_LOGI(TAG, "Battery recovered — returning to normal");
            g_low_batt_stable_s = 0;
            enter_deep_sleep(1, STATE_DEEP_SLEEP);
            return;
        }
    } else {
        g_low_batt_stable_s = 0;
        ESP_LOGW(TAG, "Battery still low: %" PRIu32 " mV", batt_mv);
    }

    /* Back to deep sleep for the check interval                    */
    enter_deep_sleep(LOW_BATT_CHECK_SECONDS, STATE_LOW_BATT);
}

/**
 * Run the NORMAL state: Pi is driving, monitor heartbeat.
 */
static void run_state_normal(void)
{
    ESP_LOGI(TAG, ">> STATE_NORMAL");

    int prev_status = gpio_get_level(PIN_PI_STATUS);
    uint32_t last_toggle_s = (uint32_t)(esp_timer_get_time() / 1000000LL);
    uint32_t last_batt_check_s = last_toggle_s;
    uint32_t heartbeat_dead_s = 0;
    uint32_t normal_enter_s = last_toggle_s;
    bool pi_alive = true;

    while (1) {
        vTaskDelay(pdMS_TO_TICKS(POLL_INTERVAL_MS));
        uint32_t now_s = (uint32_t)(esp_timer_get_time() / 1000000LL);

        /* ── Heartbeat monitor ─────────────────────────────────── */
        int curr_status = gpio_get_level(PIN_PI_STATUS);
        if (curr_status != prev_status) {
            last_toggle_s = now_s;
            heartbeat_dead_s = 0;
            pi_alive = true;
            prev_status = curr_status;
        } else {
            heartbeat_dead_s = now_s - last_toggle_s;
            if (heartbeat_dead_s >= PI_HEARTBEAT_TIMEOUT_SECONDS) {
                pi_alive = false;
            }
        }

        /* ── Pi dead? ──────────────────────────────────────────── */
        if (!pi_alive && heartbeat_dead_s >= PI_HEARTBEAT_TIMEOUT_SECONDS) {
            ESP_LOGE(TAG, "Pi heartbeat LOST for %" PRIu32 " s — Pi may be dead",
                     heartbeat_dead_s);
            /* In a full implementation, this could power-cycle the Pi.
             * For now, log the event and return to deep sleep.     */
            ESP_LOGE(TAG, "Pi is unresponsive. Returning to sentinel mode.");
            break;
        }

        /* ── Check battery every 10 s ──────────────────────────── */
        if (now_s - last_batt_check_s >= 10) {
            uint32_t batt_mv = read_battery_voltage();
            g_last_battery_mv = batt_mv;
            last_batt_check_s = now_s;

            if (batt_mv > 0 && batt_mv < BATTERY_LOW_MV) {
                ESP_LOGW(TAG, "Battery low during normal op: %" PRIu32 " mV",
                         batt_mv);
                /* Transition to LOW_BATT — Pi should save state    */
                enter_deep_sleep(LOW_BATT_CHECK_SECONDS, STATE_LOW_BATT);
                return;
            }
        }

        /* ── Safety: timeout after 2 hours ─────────────────────── */
        if (now_s - normal_enter_s > 7200) {
            ESP_LOGW(TAG, "NORMAL state timeout (2h) — returning to sleep");
            break;
        }
    }

    g_pi_dead_seconds = heartbeat_dead_s;
    enter_deep_sleep(1, STATE_DEEP_SLEEP);
}

/* ═══════════════════════════════════════════════════════════════════
 *  APP MAIN — entry point (called on every boot / deep-sleep wake)
 * ═══════════════════════════════════════════════════════════════════ */

void app_main(void)
{
    /* ── Boot banner ──────────────────────────────────────────── */
    g_boot_count++;

    esp_sleep_wakeup_cause_t wake_cause = esp_sleep_get_wakeup_cause();
    const char *cause_str =
        (wake_cause == ESP_SLEEP_WAKEUP_TIMER)  ? "timer"  :
        (wake_cause == ESP_SLEEP_WAKEUP_GPIO)   ? "GPIO"   :
        (wake_cause == ESP_SLEEP_WAKEUP_UNDEFINED) ? "cold" : "other";

    ESP_LOGI(TAG, "── VISTA Sentinel boot #%" PRIu32
             " | wake=%s | prev_state=%d | armed=%d ──",
             g_boot_count, cause_str, (int)g_state, g_armed ? 1 : 0);

    /* ── Initialise hardware ──────────────────────────────────── */
    gpio_init_all();
    adc_init();

    /* ── Quick PIR & battery snapshot ─────────────────────────── */
    g_last_pir = check_pir();
    g_last_battery_mv = read_battery_voltage();
    ESP_LOGI(TAG, "Snapshot: PIR=%s batt=%" PRIu32 " mV",
             g_last_pir ? "HIGH" : "LOW", g_last_battery_mv);

    /* ══════════════════════════════════════════════════════════
     *  STATE DISPATCH
     * ══════════════════════════════════════════════════════════ */

    switch (g_state) {

    /* ── DEEP SLEEP: periodic polling ─────────────────────────── */
    case STATE_DEEP_SLEEP: {

        if (!g_armed) {
            /* Disarmed — just sleep                               */
            ESP_LOGI(TAG, "Disarmed — sleeping %" PRIu32 " s",
                     g_deep_sleep_duration_s);
            enter_deep_sleep(g_deep_sleep_duration_s, STATE_DEEP_SLEEP);
            return;
        }

        /* ── Confirm PIR (3 samples @ 100 ms) ─────────────────── */
        if (g_last_pir) {
            bool confirmed = check_pir_confirmed(PIR_CONFIRM_COUNT,
                                                 PIR_CONFIRM_INTERVAL_MS);
            if (confirmed) {
                ESP_LOGI(TAG, "PIR MOTION CONFIRMED → ALERT");
                enter_deep_sleep(0, STATE_ALERT); /* 0-s sleep → immediate reboot */
                return;
            }
            ESP_LOGD(TAG, "PIR false trigger (not confirmed)");
        }

        /* ── Check battery ────────────────────────────────────── */
        if (g_last_battery_mv > 0 && g_last_battery_mv < BATTERY_LOW_MV) {
            ESP_LOGW(TAG, "Battery LOW (%" PRIu32 " mV) → LOW_BATT",
                     g_last_battery_mv);
            g_low_batt_stable_s = 0;
            enter_deep_sleep(0, STATE_LOW_BATT);
            return;
        }

        /* Nothing interesting — back to sleep                     */
        enter_deep_sleep(DEEP_SLEEP_US / 1000000, STATE_DEEP_SLEEP);
        return;
    }

    /* ── ALERT: motion detected ───────────────────────────────── */
    case STATE_ALERT:
        run_state_alert();
        break;

    /* ── LOW BATTERY: conservation mode ───────────────────────── */
    case STATE_LOW_BATT:
        run_state_low_batt();
        break;

    /* ── NORMAL: Pi driving, monitor heartbeat ────────────────── */
    case STATE_NORMAL:
        run_state_normal();
        break;

    default:
        ESP_LOGE(TAG, "Unknown state %d — resetting to DEEP_SLEEP",
                 (int)g_state);
        g_state = STATE_DEEP_SLEEP;
        enter_deep_sleep(1, STATE_DEEP_SLEEP);
        break;
    }

    /* Should never reach here (all paths call enter_deep_sleep)   */
    ESP_LOGE(TAG, "Unexpected exit from state machine — sleeping");
    enter_deep_sleep(1, STATE_DEEP_SLEEP);
}
