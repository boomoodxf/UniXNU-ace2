/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef ACE2_SPMI_KEYS_H_
#define ACE2_SPMI_KEYS_H_

#include <Uefi.h>

enum {
  SK_VERSION_V7_MIN = 0x70000000u, SK_VERSION_V8_MIN = 0x80000000u,
  SK_FEATURES = 0x04, SK_FEATURES_APIDS_MASK = 0x7ffu,
  SK_APID_MAP = 0x2000,
  SK_OBS_EE_STRIDE = 0x8000, SK_OBS_APID_STRIDE = 0x20,
  SK_CMD = 0x00, SK_STATUS = 0x08, SK_RDATA0 = 0x18,
  SK_OP_EXT_READL = 1,
  SK_STATUS_DONE = 1u << 0, SK_STATUS_ERRORS = 0xeu,
  SK_POLLS = 100000,
  SK_PPID_PON = 0x013, SK_PPID_GPIO6 = 0x18d, SK_REG_RT_STS = 0x10,
  SK_REG_GPIO_STS = 0x08,
  SK_PON_RESIN = 1u << 6, SK_PON_KPDPWR = 1u << 7,
  SK_KEY_POWER = 1u << 0, SK_KEY_VOLDOWN = 1u << 1, SK_KEY_VOLUP = 1u << 2
};

struct sk_arbiter {
  volatile UINT32 *core;
  volatile UINT32 *obs;
  UINT8 ee;
};

static inline int sk_find_apid (const struct sk_arbiter *a, UINT32 ppid, int *apid)
{
  UINT32 version = a->core[0], apids = a->core[SK_FEATURES / 4] & SK_FEATURES_APIDS_MASK;
  *apid = -1;
  if (version < SK_VERSION_V7_MIN || version >= SK_VERSION_V8_MIN) return 1;
  if (!apids || apids > 1024) return 2;
  for (UINT32 i = 0; i < apids; ++i) {
    UINT32 map = a->core[(SK_APID_MAP + 4 * i) / 4];
    if (map && ((map >> 8) & 0xfff) == ppid) { *apid = (int) i; break; }
  }
  return *apid < 0 ? 3 : 0;
}

static inline int sk_read8 (const struct sk_arbiter *a, int apid, UINT8 reg, UINT8 *value)
{
  volatile UINT32 *ch = a->obs + (SK_OBS_EE_STRIDE * a->ee + SK_OBS_APID_STRIDE * (UINT32) apid) / 4;
  ch[SK_CMD / 4] = ((UINT32) SK_OP_EXT_READL << 27) | ((UINT32) reg << 4);
  for (unsigned n = 0; n < SK_POLLS; ++n) {
    UINT32 s = ch[SK_STATUS / 4];
    if (s & SK_STATUS_DONE) {
      if (s & SK_STATUS_ERRORS) return 2;
      *value = (UINT8) ch[SK_RDATA0 / 4];
      return 0;
    }
  }
  return 1;
}

struct sk_keys { int pon, gpio; UINT8 pon_base, g8_base, g10_base; };

static inline int sk_open (const struct sk_arbiter *a, struct sk_keys *k)
{
  int rc = sk_find_apid (a, SK_PPID_PON, &k->pon);
  if (rc) return rc;
  if (sk_find_apid (a, SK_PPID_GPIO6, &k->gpio)) k->gpio = -1;
  k->pon_base = 0;
  k->g8_base = 0;
  k->g10_base = 0;
  if (sk_read8 (a, k->pon, SK_REG_RT_STS, &k->pon_base)) return 4;
  if (k->gpio >= 0) {
    int r8 = sk_read8 (a, k->gpio, 0x08, &k->g8_base);
    int r10 = sk_read8 (a, k->gpio, 0x10, &k->g10_base);
    if (r8 && r10) k->gpio = -1;
  }
  return 0;
}

static inline int sk_sample (const struct sk_arbiter *a, const struct sk_keys *k, UINT8 *pressed)
{
  UINT8 v = 0, d, g8 = 0, g10 = 0;
  *pressed = 0;
  int rc = sk_read8 (a, k->pon, SK_REG_RT_STS, &v);
  if (rc) return rc;
  d = (UINT8) (v ^ k->pon_base);
  if (d & (SK_PON_KPDPWR | (1u << 7))) *pressed |= SK_KEY_POWER;
  if (d & (SK_PON_RESIN | (1u << 6))) *pressed |= SK_KEY_VOLUP;
  if (k->gpio >= 0) {
    if (!sk_read8 (a, k->gpio, 0x08, &g8) && ((g8 ^ k->g8_base) & 0x41)) *pressed |= SK_KEY_VOLDOWN;
    if (!sk_read8 (a, k->gpio, 0x10, &g10) && ((g10 ^ k->g10_base) & 0x41)) *pressed |= SK_KEY_VOLDOWN;
  }
  return 0;
}

struct sk_filter { UINT8 last, stable; UINT16 held[3]; };

static inline UINT8 sk_step (struct sk_filter *f, UINT8 sample, UINT16 delay, UINT16 period)
{
  UINT8 out = 0;
  if (sample == f->last) {
    UINT8 fresh = (UINT8) (sample & ~f->stable);
    f->stable = sample;
    out = fresh;
    for (unsigned i = 0; i < 3; ++i) {
      UINT8 bit = (UINT8) (1u << i);
      if (!(sample & bit)) { f->held[i] = 0; continue; }
      if (fresh & bit) { f->held[i] = 0; continue; }
      ++f->held[i];
      if (bit != SK_KEY_POWER && f->held[i] >= delay && (f->held[i] - delay) % period == 0) out |= bit;
    }
  }
  f->last = sample;
  return out;
}

#endif
