# ─────────────────────────────────────────────
#  SmartQualityControl — report.py
#  Automated shift report generator (PDF)
# ─────────────────────────────────────────────

import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import List

try:
    from fpdf import FPDF
    _FPDF_AVAILABLE = True
except ImportError:
    _FPDF_AVAILABLE = False


@dataclass
class InspectionRecord:
    timestamp:    str
    total:        int
    defects:      int
    rate:         float
    is_defective: bool


@dataclass
class ShiftReport:
    start_time: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    records:    List[InspectionRecord] = field(default_factory=list)

    # ── Data collection ───────────────────────
    def add_record(self, total: int, defects: int, rate: float, is_defective: bool):
        self.records.append(InspectionRecord(
            timestamp    = datetime.now().strftime("%H:%M:%S"),
            total        = total,
            defects      = defects,
            rate         = rate,
            is_defective = is_defective,
        ))

    # ── Statistics ────────────────────────────
    def summary(self) -> dict:
        if not self.records:
            return {}
        rates   = [r.rate for r in self.records]
        last    = self.records[-1]
        return {
            'total_products': last.total,
            'total_defects':  last.defects,
            'avg_rate':       sum(rates) / len(rates),
            'max_rate':       max(rates),
            'inspections':    len(self.records),
            'duration_min':   len(self.records) * 2 / 60,  # ~2s per cycle
        }

    # ── PDF export ────────────────────────────
    def save_pdf(self, output_dir: str = ".") -> str:
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(output_dir, f"shift_report_{timestamp}.pdf")

        if not _FPDF_AVAILABLE:
            txt_path = path.replace(".pdf", ".txt")
            self._save_txt(txt_path)
            return txt_path

        self._save_pdf_fpdf(path)
        return path

    def _save_txt(self, path: str):
        s = self.summary()
        lines = [
            "=" * 50,
            "SMARTQUALITYCONTROL — SHIFT REPORT",
            "=" * 50,
            f"Shift start  : {self.start_time}",
            f"Report time  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "SUMMARY",
            "-" * 30,
            f"Total products  : {s.get('total_products', 0)}",
            f"Total defects   : {s.get('total_defects', 0)}",
            f"Average rate    : {s.get('avg_rate', 0):.1f}%",
            f"Peak rate       : {s.get('max_rate', 0):.1f}%",
            f"Inspections     : {s.get('inspections', 0)}",
            f"Duration (est.) : {s.get('duration_min', 0):.1f} min",
            "",
            "INSPECTION LOG (last 30)",
            "-" * 30,
        ]
        for rec in self.records[-30:]:
            flag = "DEF" if rec.is_defective else " OK"
            lines.append(
                f"{rec.timestamp}  [{flag}]  "
                f"Total:{rec.total:4d}  Defects:{rec.defects:4d}  Rate:{rec.rate:5.1f}%"
            )
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _save_pdf_fpdf(self, path: str):
        s = self.summary()
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # ── Header
        pdf.set_fill_color(40, 42, 54)
        pdf.rect(0, 0, 210, 30, "F")
        pdf.set_text_color(189, 147, 249)
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 20, "SmartQualityControl", ln=True, align="C")
        pdf.set_text_color(98, 114, 164)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 8, "Shift Quality Report", ln=True, align="C")
        pdf.ln(6)

        # ── Meta
        pdf.set_text_color(80, 80, 80)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, f"Shift start: {self.start_time}", ln=True)
        pdf.cell(0, 6, f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
        pdf.ln(4)

        # ── Summary box
        _section_header(pdf, "Summary")
        _kv(pdf, "Total products inspected", str(s.get('total_products', 0)))
        _kv(pdf, "Total defects detected",   str(s.get('total_defects', 0)))
        _kv(pdf, "Average defect rate",      f"{s.get('avg_rate', 0):.1f}%")
        _kv(pdf, "Peak defect rate",         f"{s.get('max_rate', 0):.1f}%")
        _kv(pdf, "Total inspections",        str(s.get('inspections', 0)))
        _kv(pdf, "Estimated duration",       f"{s.get('duration_min', 0):.1f} min")
        pdf.ln(4)

        # ── Rate trend (simple ASCII bar)
        if self.records:
            _section_header(pdf, "Defect Rate Trend (sampled)")
            pdf.set_font("Courier", "", 8)
            pdf.set_text_color(60, 60, 60)
            sample = self.records[::max(1, len(self.records) // 20)]
            for rec in sample:
                bar_len = int(rec.rate / 2)
                bar = "|" * bar_len
                line = f"{rec.timestamp}  {rec.rate:5.1f}%  {bar}"
                pdf.cell(0, 5, line, ln=True)
            pdf.ln(4)

        # ── Inspection log table
        _section_header(pdf, "Inspection Log (last 50)")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(68, 71, 90)
        pdf.set_text_color(248, 248, 242)
        pdf.cell(22, 6, "Time", border=1, fill=True)
        pdf.cell(14, 6, "Status", border=1, fill=True)
        pdf.cell(24, 6, "Total", border=1, fill=True)
        pdf.cell(24, 6, "Defects", border=1, fill=True)
        pdf.cell(24, 6, "Rate %", border=1, fill=True, ln=True)

        pdf.set_font("Helvetica", "", 8)
        for i, rec in enumerate(self.records[-50:]):
            bg = (255, 235, 235) if rec.is_defective else (235, 255, 235)
            pdf.set_fill_color(*bg)
            pdf.set_text_color(40, 42, 54)
            status = "DEFECTIVE" if rec.is_defective else "OK"
            pdf.cell(22, 5, rec.timestamp,    border=1, fill=True)
            pdf.cell(14, 5, status,           border=1, fill=True)
            pdf.cell(24, 5, str(rec.total),   border=1, fill=True)
            pdf.cell(24, 5, str(rec.defects), border=1, fill=True)
            pdf.cell(24, 5, f"{rec.rate:.1f}", border=1, fill=True, ln=True)

        pdf.output(path)


# ─────────────────────────────────────────────
#  PDF helpers
# ─────────────────────────────────────────────
def _section_header(pdf: "FPDF", title: str):
    pdf.set_fill_color(68, 71, 90)
    pdf.set_text_color(189, 147, 249)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, f"  {title}", ln=True, fill=True)
    pdf.set_text_color(40, 42, 54)
    pdf.ln(1)


def _kv(pdf: "FPDF", key: str, value: str):
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(70, 6, key + ":", border=0)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 42, 54)
    pdf.cell(0, 6, value, ln=True)


# ─────────────────────────────────────────────
#  CLI usage: python report.py  (generates a demo report)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import random
    print("Generating demo shift report...")
    rpt = ShiftReport()
    total = 0
    defects = 0
    for i in range(80):
        total += 1
        is_def = random.random() < 0.12
        if is_def:
            defects += 1
        rate = defects / total * 100
        rpt.add_record(total, defects, rate, is_def)

    path = rpt.save_pdf(output_dir="..")
    print(f"Report saved: {path}")
