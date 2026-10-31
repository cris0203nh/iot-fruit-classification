#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace agroscan {
// Starting values for bench tests; not validated accuracy specifications.
constexpr size_t WINDOW = 10;
constexpr uint32_t TIMEOUT_MS = 1500;
constexpr uint32_t MAX_GAP_MS = 400;
constexpr double STABLE_SPAN_G = 2.0;
constexpr double ZERO_BAND_G = 2.0;
constexpr double RAW_SPAN = 200.0;
constexpr double MAX_WEIGHT_G = 5000.0;

struct Calibration {
  double offset = 0;
  double counts_per_gram = 0;
  uint32_t revision = 0;
};
struct Reading {
  const char* status;
  bool valid;
  bool stable;
  double weight_g;
};

class ScaleCore {
  double samples_[WINDOW] = {};
  size_t count_ = 0, next_ = 0;
  uint32_t last_ = 0;
  bool seen_ = false, healthy_ = false, zero_ = false;
  Calibration calibration_;
 public:
  void clearWindow() { count_ = 0; next_ = 0; }
  void restore(const Calibration& c) {
    calibration_ = c;
    if (!std::isfinite(c.offset) || !std::isfinite(c.counts_per_gram)
        || std::abs(c.counts_per_gram) < 1e-6 || c.revision == 0) {
      calibration_ = Calibration{};
    }
    bool zeroConfirmed() const {
    return zero_;
}
    clearWindow();
  }
  const Calibration& calibration() const { return calibration_; }
  void fault() { healthy_ = false; clearWindow(); }
  bool add(int32_t raw, uint32_t now) {
    if (raw <= -8388608 || raw >= 8388607) { fault(); return false; }
    if (!healthy_ || (seen_ && uint32_t(now-last_) > MAX_GAP_MS)) clearWindow();
    seen_ = healthy_ = true; last_ = now;
    samples_[next_] = raw; next_ = (next_ + 1) % WINDOW;
    if (count_ < WINDOW) ++count_;
    return true;
  }
  bool fresh(uint32_t now) const {
    return seen_ && healthy_ && uint32_t(now-last_) <= TIMEOUT_MS;
  }
  double mean() const {
    double sum = 0; for (size_t i=0;i<count_;++i) sum += samples_[i];
    return count_ ? sum/count_ : 0;
  }
  double span() const {
    if (!count_) return 0;
    double lo=samples_[0], hi=lo;
    for (size_t i=1;i<count_;++i) { if(samples_[i]<lo)lo=samples_[i]; if(samples_[i]>hi)hi=samples_[i]; }
    return hi-lo;
  }
  bool rawStable(uint32_t now) const { return fresh(now) && count_ == WINDOW && span() <= RAW_SPAN; }
  bool tare(uint32_t now) {
    if (!rawStable(now) || calibration_.revision == UINT32_MAX) return false;
    if (calibration_.revision) ++calibration_.revision; // Offset changes are versioned too.
    calibration_.offset = mean(); zero_ = true; clearWindow(); return true;
  }
  bool calibrate(double grams, uint32_t now) {
    if (!zero_ || !rawStable(now) || !std::isfinite(grams) || grams <= 0 || grams > MAX_WEIGHT_G) return false;
    double delta = mean()-calibration_.offset;
    if (std::abs(delta) < 1000 || calibration_.revision == UINT32_MAX) return false;
    double factor = delta/grams;
    if (!std::isfinite(factor) || std::abs(factor) < 1e-6) return false;
    calibration_.counts_per_gram = factor; ++calibration_.revision;
    clearWindow(); return true;
  }
  Reading reading(uint32_t now) const {
    if (!fresh(now)) return {"sensor_unavailable",false,false,0};
    if (calibration_.revision == 0) return {"uncalibrated",false,false,0};
    if (!zero_) return {"zero_required",false,false,0};
    if (count_ < WINDOW) return {"warming_up",false,false,0};
    double w = (mean()-calibration_.offset)/calibration_.counts_per_gram;
    if (!std::isfinite(w) || w < -ZERO_BAND_G || w > MAX_WEIGHT_G) return {"out_of_range",false,false,0};
    if (std::abs(w) <= ZERO_BAND_G) w=0; // Explicit provisional zero band.
    bool stable = span()/std::abs(calibration_.counts_per_gram) <= STABLE_SPAN_G;
    return {stable ? "stable" : "unstable",true,stable,w};
  }
};
} // namespace agroscan
