// Feather9x_SerialTX
// Type a message in the serial console and press Enter to send it.
//   MODE_LORA  - messages are sent as LoRa packets (default)
//   MODE_CW    - messages are sent as Morse code by keying the carrier on/off
// Incoming LoRa packets are printed as they arrive (LoRa mode only).
// Based on the Adafruit Feather9x_TX example. KM7HZC

#include <SPI.h>
#include <RH_RF95.h>
#include <avr/pgmspace.h>

#if defined (__AVR_ATmega32U4__)  // Feather 32u4 w/Radio
  #define RFM95_CS    8
  #define RFM95_INT   7
  #define RFM95_RST   4
#endif

// Must match the receiver's frequency!
#define RF95_FREQ 433.0

// Optional: prefix added to every outgoing LoRa message (set to "" to disable)
#define MSG_PREFIX "KM7HZC: "

// CW speed in words per minute. One dit lasts 1200 / WPM milliseconds.
#define CW_WPM 15

RH_RF95 rf95(RFM95_CS, RFM95_INT);

// ---------------------------------------------------------------------------
// Operating mode
// ---------------------------------------------------------------------------
enum Mode { MODE_LORA, MODE_CW };
Mode currentMode = MODE_LORA;

// ---------------------------------------------------------------------------
// Serial line buffer
// ---------------------------------------------------------------------------
const uint8_t MAX_INPUT = RH_RF95_MAX_MESSAGE_LEN - sizeof(MSG_PREFIX);
char inputBuf[MAX_INPUT + 1];
uint8_t inputLen = 0;

// ---------------------------------------------------------------------------
// SX1276 registers used for CW (FSK/OOK modem). See the SX1276 datasheet.
// ---------------------------------------------------------------------------
#define REG_OPMODE          0x01
#define REG_FDEV_MSB        0x04
#define REG_FDEV_LSB        0x05
#define REG_FRF_MSB         0x06
#define REG_FRF_MID         0x07
#define REG_FRF_LSB         0x08
#define REG_PA_RAMP         0x0A
#define REG_PACKET_CONFIG2  0x31

// RegOpMode values for the FSK modem. Bit 7 = 0 selects FSK/OOK instead of
// LoRa; bit 3 = 1 selects the low-frequency register bank (below 525 MHz).
#define OPMODE_LORA_SLEEP   0x80
#define OPMODE_FSK_SLEEP    0x08
#define OPMODE_FSK_STANDBY  0x09
#define OPMODE_FSK_FSTX     0x0A  // synthesizer locked, PA off ("key up")
#define OPMODE_FSK_TX       0x0B  // transmitting carrier ("key down")

// ---------------------------------------------------------------------------
// Morse table, stored in flash (PROGMEM) to save the 32u4's limited RAM
// ---------------------------------------------------------------------------
struct MorseEntry {
  char ch;
  char code[8];
};

const MorseEntry MORSE_TABLE[] PROGMEM = {
  {'A', ".-"},    {'B', "-..."},  {'C', "-.-."},  {'D', "-.."},
  {'E', "."},     {'F', "..-."},  {'G', "--."},   {'H', "...."},
  {'I', ".."},    {'J', ".---"},  {'K', "-.-"},   {'L', ".-.."},
  {'M', "--"},    {'N', "-."},    {'O', "---"},   {'P', ".--."},
  {'Q', "--.-"},  {'R', ".-."},   {'S', "..."},   {'T', "-"},
  {'U', "..-"},   {'V', "...-"},  {'W', ".--"},   {'X', "-..-"},
  {'Y', "-.--"},  {'Z', "--.."},
  {'0', "-----"}, {'1', ".----"}, {'2', "..---"}, {'3', "...--"},
  {'4', "....-"}, {'5', "....."}, {'6', "-...."}, {'7', "--..."},
  {'8', "---.."}, {'9', "----."},
  {'.', ".-.-.-"}, {',', "--..--"}, {'?', "..--.."}, {'/', "-..-."},
  {'=', "-...-"},  {'-', "-....-"}, {'+', ".-.-."},  {'@', ".--.-."},
};
const uint8_t MORSE_TABLE_LEN = sizeof(MORSE_TABLE) / sizeof(MORSE_TABLE[0]);

// ===========================================================================
// Setup
// ===========================================================================

// Reset the radio and put it in LoRa mode with our settings.
// Used at startup and when switching back from CW.
bool setupLoRa() {
  // Hardware reset returns every register to its power-on default,
  // which cleanly undoes everything CW mode changed.
  digitalWrite(RFM95_RST, LOW);
  delay(10);
  digitalWrite(RFM95_RST, HIGH);
  delay(10);

  if (!rf95.init()) {
    Serial.println("LoRa radio init failed");
    return false;
  }
  if (!rf95.setFrequency(RF95_FREQ)) {
    Serial.println("setFrequency failed");
    return false;
  }

  // Long-range modem settings (must match the RX board)
  rf95.setSignalBandwidth(125000);
  rf95.setSpreadingFactor(12);
  rf95.setCodingRate4(8);

  rf95.setTxPower(23, false);
  return true;
}

void setup() {
  pinMode(RFM95_RST, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);

  Serial.begin(115200);
  while (!Serial) delay(1);
  delay(100);

  Serial.println("Feather LoRa/CW Serial TX by KM7HZC");

  if (!setupLoRa()) {
    while (1);
  }
  Serial.println("LoRa radio init OK!");
  Serial.print("Freq: "); Serial.print(RF95_FREQ); Serial.println(" MHz");

  Serial.println("Type a message and press Enter to send.");
  Serial.println("Type MODE_CW or MODE_LORA to switch modes.");
  printPrompt();
}

// ===========================================================================
// CW (Morse) mode
// ===========================================================================

// Write the carrier frequency into the radio's Frf registers.
// Frf = frequency_Hz / (32 MHz / 2^19)
void setFrfRegisters(float mhz) {
  uint64_t hz = (uint64_t)(mhz * 1000000.0);
  uint32_t frf = (uint32_t)((hz << 19) / 32000000UL);
  rf95.spiWrite(REG_FRF_MSB, (frf >> 16) & 0xFF);
  rf95.spiWrite(REG_FRF_MID, (frf >> 8) & 0xFF);
  rf95.spiWrite(REG_FRF_LSB, frf & 0xFF);
}

// Switch the radio from LoRa into FSK continuous mode with zero deviation.
// With no deviation, "transmit" produces a plain unmodulated carrier,
// which we switch on and off to send Morse.
void enterCWMode() {
  rf95.setModeIdle();

  // The LoRa/FSK modem can only be changed while the chip is asleep.
  rf95.spiWrite(REG_OPMODE, OPMODE_LORA_SLEEP);
  rf95.spiWrite(REG_OPMODE, OPMODE_FSK_SLEEP);
  delay(10);
  rf95.spiWrite(REG_OPMODE, OPMODE_FSK_STANDBY);

  setFrfRegisters(RF95_FREQ);

  rf95.spiWrite(REG_FDEV_MSB, 0x00);        // frequency deviation = 0
  rf95.spiWrite(REG_FDEV_LSB, 0x00);
  rf95.spiWrite(REG_PACKET_CONFIG2, 0x00);  // continuous mode (no packets/FIFO)
  rf95.spiWrite(REG_PA_RAMP, 0x00);         // slowest PA ramp (3.4 ms) to soften key clicks

  // Lock the synthesizer with the PA off, ready for fast keying.
  // Power-amp settings from setTxPower() carry over from LoRa mode.
  rf95.spiWrite(REG_OPMODE, OPMODE_FSK_FSTX);
  delay(1);
}

void keyDown() { rf95.spiWrite(REG_OPMODE, OPMODE_FSK_TX); }
void keyUp()   { rf95.spiWrite(REG_OPMODE, OPMODE_FSK_FSTX); }

// Look up a character's Morse pattern. Returns false if it isn't in the table.
bool lookupMorse(char c, char *out) {
  for (uint8_t i = 0; i < MORSE_TABLE_LEN; i++) {
    if (pgm_read_byte(&MORSE_TABLE[i].ch) == c) {
      strcpy_P(out, MORSE_TABLE[i].code);
      return true;
    }
  }
  return false;
}

// Send a whole line as Morse. This blocks until the line is finished.
void sendCW(const char *text) {
  const unsigned int dit = 1200 / CW_WPM;
  char code[8];

  Serial.print("Keying: ");
  for (const char *p = text; *p; p++) {
    char c = toupper(*p);

    if (c == ' ') {
      // Word gap is 7 dits. 3 were already spent after the previous letter.
      delay(4 * dit);
      Serial.print(' ');
      continue;
    }

    if (!lookupMorse(c, code)) {
      continue;  // skip characters with no Morse equivalent
    }

    for (char *e = code; *e; e++) {
      keyDown();
      delay(*e == '-' ? 3 * dit : dit);  // dah = 3 dits, dit = 1 dit
      keyUp();
      delay(dit);                         // gap between elements = 1 dit
    }
    delay(2 * dit);  // letter gap is 3 dits total (1 already spent above)

    Serial.print(c);
  }
  keyUp();  // make sure the carrier is off
  Serial.println();
  Serial.println("Done.");
}

// ===========================================================================
// LoRa mode
// ===========================================================================

void sendLine() {
  char packet[RH_RF95_MAX_MESSAGE_LEN];
  snprintf(packet, sizeof(packet), "%s%s", MSG_PREFIX, inputBuf);
  uint8_t len = strlen(packet) + 1;  // include the null terminator so RX can print it

  Serial.print("Sending: "); Serial.println(packet);
  rf95.send((uint8_t *)packet, len);
  rf95.waitPacketSent();
  Serial.println("Sent.");
}

void checkRadio() {
  if (rf95.available()) {
    uint8_t buf[RH_RF95_MAX_MESSAGE_LEN];
    uint8_t len = sizeof(buf) - 1;
    if (rf95.recv(buf, &len)) {
      buf[len] = 0;  // make sure it's null-terminated before printing
      Serial.println();
      Serial.print("Received: ");
      Serial.println((char *)buf);
      Serial.print("RSSI: ");
      Serial.println(rf95.lastRssi(), DEC);
      printPrompt();
      Serial.write(inputBuf, inputLen);  // redraw anything you were typing
    }
  }
}

// ===========================================================================
// Serial input and commands
// ===========================================================================

void printPrompt() {
  Serial.print(currentMode == MODE_CW ? "[CW]> " : "[LORA]> ");
}

// Called when Enter is pressed. Either switches modes or sends the line.
void handleLine() {
  if (strcasecmp(inputBuf, "MODE_CW") == 0) {
    if (currentMode != MODE_CW) {
      enterCWMode();
      currentMode = MODE_CW;
    }
    Serial.print("CW mode, "); Serial.print(CW_WPM); Serial.println(" WPM.");

  } else if (strcasecmp(inputBuf, "MODE_LORA") == 0) {
    if (currentMode != MODE_LORA) {
      if (!setupLoRa()) {
        while (1);
      }
      currentMode = MODE_LORA;
    }
    Serial.println("LoRa mode.");

  } else if (currentMode == MODE_CW) {
    sendCW(inputBuf);

  } else {
    sendLine();
  }
}

void checkSerial() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\r' || c == '\n') {
      // Enter pressed. Ignore empty lines (also swallows the \n of a \r\n pair).
      if (inputLen > 0) {
        Serial.println();
        inputBuf[inputLen] = '\0';
        handleLine();
        inputLen = 0;
        printPrompt();
      }
    } else if (c == '\b' || c == 127) {
      // Backspace (useful in terminal programs like PuTTY or screen)
      if (inputLen > 0) {
        inputLen--;
        Serial.print("\b \b");
      }
    } else if (inputLen < MAX_INPUT) {
      inputBuf[inputLen++] = c;
      Serial.print(c);  // echo, so you can see what you type in a terminal
    }
    // Characters beyond MAX_INPUT are dropped
  }
}

void loop() {
  checkSerial();

  // Only poll for LoRa packets in LoRa mode. rf95.available() puts the chip
  // into LoRa receive, which would break CW mode.
  if (currentMode == MODE_LORA) {
    checkRadio();
  }
}
