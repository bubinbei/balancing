---
updated: 2026-10-30
status: hardware_inputs_required
current_task: G00
---

# Текущее состояние

После P00: BLC1/CRC, CONFIG/session/epoch, raw/replay, команды/PySerial, 1×/FFT/angular average, две плоскости, bootstrap. C99: кодек, очередь, timebase, LE16/HR12; native Release/CTest.

Владелец подтвердил: NiceNano — недорогой клон; заказаны два BMI160, два LIS3DH и KY-033. Ревизия/схема, INFO_UF2.TXT/Flash layout, фактические GPIO, питание и геометрия ротора неизвестны. G00/G01 blocked; G06 blocked на размерах/нагрузках. G02/G04/G07/G11/G12/G13/G14 in_progress: подготовка и synthetic-проверки, без полной приёмки зависимостей. G03/G05/G08/G09/G10 planned.

Коленвал со слов владельца 13,05 кг; люлька оценочно 1–2 кг. Полная масса с маховиком/шкивом неизвестна. Паспорт/условный пересчёт: hardware/rotor-passport.md, docs/MECHANICS.md.

70 Python-тестов/1 CTest проверены ранее; отчёты: evidence/reports/AUDIT_PACKAGE.md и G07.md. Нынешний раунд — документация, приборы не использовались.

Первый ввод: docs/CALIBRATION_PROTOCOL.md — обучение A/B, слепой поиск r/x/угла одной известной добавки, нулевые пробы, обратимая коррекция. Методика planned; мастер/локализация не реализованы.

Механика: docs/COASTDOWN_PROTOCOL.md и docs/ROLLER_SUPPORT_CONCEPT.md — выбег и четыре ролика 6200. Опоры не приняты; G06 blocked. Владелец заказал JGB37-520, экземпляр не проверен.

Экран: uv run balancing demo --open. 3D с прозрачной люлькой, A/B, CW1–CW8, учебный перенос снятия. Проверены Chrome 320/360/1280 и перекрытие поверхностей. Отчёт: evidence/reports/G07/analysis-review.md. BLC1/USB в UI нет.

D12–D14: docs/RETRACTABLE_DRIVE.md — два тахосигнала, отвод и анализ выбега. Владелец выбрал RDS3115 (hardware/servo-passport.md). docs/PIN_BUDGET.md/CSV: 23 прямых GPIO с OLED; предложен MCP23017 для двух медленных входов, остаётся 21. Клон/распиновка/механизм не приняты, управление planned.

Плата, COM и привод не использовались. Образа NiceNano/SPI-IRQ-USB adapter нет; физические 90 минут, смазка/защита, реальные грузы и остаток не проверены. 100 г·мм: not_tested. Финальный аудит не готов.

Следующее: получить детали и паспорт клона/ротора, обмерить шейки и обод привода; закрыть G00 → G01/G06. Программный demo: uv sync --frozen; см. host/README.md. Публичные GitHub/Gitea содержат исходники; raw/build локальны.
