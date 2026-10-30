# Первичные источники

Проверены при подготовке плана 2026-10-28. Ссылки ведут к производителям, авторам и официальным учебным материалам. Чужие исходники и полные документы в репозиторий не копируются. Численные примеры в документации — самостоятельные расчёты, не реальные измерения.

## Контроллер и плата

| ID | Источник | Что проверять |
|---|---|---|
| N01 | [Nordic nRF52840 Product Specification v1.7](https://docs-be.nordicsemi.com/bundle/nRF52-Series-PS/raw/resource/enus/nRF52840_PS_v1.7.pdf) | SPIM, TIMER, GPIOTE/PPI, EasyDMA, USBD, ресурсы и ограничения |
| N02 | [Nordic TIMER](https://docs.nordicsemi.com/r/bundle/ps_nrf52840/page/timer.html) | Capture, частоты, разрядность, переполнение |
| N03 | [NiceNano: документация производителя](https://nicekeyboards.com/docs/nice-nano/) | nRF52840, USB/UF2, питание, загрузчик |
| N04 | [NiceNano: pinout и схемы v1/v2](https://nicekeyboards.com/docs/nice-nano/pinout-schematic/) | Ревизия, реальные GPIO, VCC switch; не переносить v1 на v2 |
| N05 | [NiceNano: getting started](https://nicekeyboards.com/docs/nice-nano/getting-started/) | Работа с платой и загрузчиком |
| N06 | [Zephyr: promicro_nrf52840, описание board family](https://github.com/zephyrproject-rtos/zephyr/blob/main/boards/others/promicro_nrf52840/doc/index.rst) | Только ориентир поддержки; зафиксировать release и совместимость фактической платы до сборки |
| N07 | [Nordic SPIM HAL: дискретные частоты](https://docs.nordicsemi.com/r/bundle/nrf5_sdk_v15.0.0/page/group_nrf_spim_hal.html) | 4/8/16/32 МГц; это справочник периферии, не выбор старого SDK для проекта |

## Датчики

| ID | Источник | Что проверять |
|---|---|---|
| S01 | [Bosch BMI160, datasheet rev 1.0, 2020](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmi160-ds000.pdf) | ODR, accel/gyro, SPI, FIFO, DRDY, sensor time, диапазоны и шум |
| S02 | [ST LIS3DH, datasheet rev 2](https://www.st.com/resource/en/datasheet/lis3dh.pdf) | HR 12 бит, полоса ODR/9, SPI 10 МГц, I2C 400 кГц, BDU/DRDY |
| S03 | [Vishay TCRT5000](https://www.vishay.com/docs/83760/tcrt5000.pdf) | Оптический элемент; свойства готового модуля проверяются отдельно |
| S04 | [Analog Devices AN-688](https://www.analog.com/en/resources/app-notes/an-688_0.html) | Фазовая/частотная характеристика датчиков и фильтров |
| S05 | [Bosch FAE: статус BMI160](https://community.bosch-sensortec.com/mems-sensors-forum-jrmujtaw/post/bmi160-switching-to-spi-slUFHuyAmTFiXvp?highlight=DVNuTlhs0Ld33J1) | BMI160 EOL; не обещать бессрочную доступность и проверять реальные модули |

## Механика и измерения

| ID | Источник | Что подтверждает |
|---|---|---|
| M01 | [Schenck: балансировка коленвалов](https://www.schenck-rotec.com/en-de/product/crankshafts) | Возможность опор скольжения/роликов; не характеристики нашего стенда |
| M02 | [IRD: soft-bearing sensitivity and speed](https://shop.irdproducts.com/blog/balancing-machines-sensitivity-and-speed/) | Работа мягких опор выше собственной частоты |
| M03 | [MAHLE: bearing failure prevention](https://www.mahle-aftermarket.com/na/en/support/installation-tips/bearings-failure-prevention.jsp) | Масляный клин и непрерывное снабжение маслом |
| M04 | [Motorservice: engine bearing system](https://www.ms-motorservice.com/MediaAssets/2054034_ks_50003859-02_web.pdf) | Постель, зазор, жёсткость и затяжка подшипника |
| M05 | [LIGO: Flexure Rods, 2004](https://dcc-lho.ligo.org/public/0044/C040117/001/20007235-D_LIGO_Flexure_Rods.pdf) | Модель натянутого круглого упругого подвеса; не расчёт наших зажимов |
| M06 | [Hilton: bifilar/trifilar suspension](https://www.p-a-hilton.co.uk/products/vibration-hvt/bifilar-trifilar-suspension) | Измерительное применение подвесок |
| M07 | [US Forest Service: moisture and dimensional changes](https://research.fs.usda.gov/treesearch/7143) | Влажность и стабильность деревянных конструкций |
| M08 | [PCB Piezotronics: sensor mounting](https://www.pcb.com/resources/technical-information/mounting) | Жёсткость крепления датчика |
| M09 | [OpenStax: pendulums](https://openstax.org/books/university-physics-volume-1/pages/15-4-pendulums) | Частота маятника и её допущения |
| M10 | [OpenStax: stress, strain, elastic modulus](https://openstax.org/books/university-physics-volume-1/pages/12-3-stress-strain-and-elastic-modulus) | Вывод осевой жёсткости EA/L; свойства конкретной проволоки измеряются отдельно |
| M11 | [OpenStax: damped oscillations](https://openstax.org/books/university-physics-volume-1/pages/15-5-damped-oscillations) | Спад огибающей и время затухания |
| M12 | [Stieber, product catalog, 05/25](https://www.stieberclutch.com/~/media/505E05375ABA49D09273439359632287.ashx) | Drag torque обгонных муфт; не гарантия полного механического разобщения |

## Обработка

| ID | Источник | Что подтверждает |
|---|---|---|
| A01 | [Brüel & Kjær: Static and Dynamic Balancing of Rigid Rotors](https://www.bksv.com/doc/bo0276.pdf) | Две плоскости, пробные грузы и фаза |
| A02 | [NPTEL: influence coefficients](https://archive.nptel.ac.in/content/storage2/courses/112103024/module13/lec4/2.html) | Получение матрицы откликов пробными грузами |
| A03 | [Dewesoft: order tracking manual](https://downloads.dewesoft.com/manuals/dewesoft-order-tracking-manual-en.pdf) | Угловая привязка и несколько меток на оборот |
| A04 | [Brüel & Kjær: coast-down order tracking](https://www.bksv.com/doc/bo0469.pdf) | Анализ амплитуды/фазы на выбеге |
| A05 | [OpenStax: rotational dynamics](https://openstax.org/books/university-physics-volume-1/pages/10-7-newtons-second-law-for-rotation) | Момент, инерция, угловое ускорение |
| A06 | [OpenStax: gyroscope](https://openstax.org/books/university-physics-volume-1/pages/11-4-precession-of-a-gyroscope) | Гироскопические моменты при изменении направления оси |

Планы проверок и выбранные инженерные пороги — наши проектные решения. Наличие ссылки не означает аппаратную или нормативную приёмку. При реализации проверять изменения документации производителя и фиксировать использованную ревизию.

## Средства сборки — дополнение 2026-10-29

| ID | Источник | Что проверено |
|---|---|---|
| T01 | [uv: caching and cache-keys](https://docs.astral.sh/uv/concepts/cache/) | Ключи локальных исходников для обновления non-editable wheel; установленный пакет дополнительно сравнивается с проектом побайтно |

## Отводимый привод — дополнение 2026-10-30

| ID | Источник | Что подтверждает |
|---|---|---|
| R01 | [Pololu: RC servo electrical interface](https://www.pololu.com/blog/16/electrical-characteristics-of-servos-and-introduction-to-the-servo-control-interface) | Команда положения импульсами, питание и общий провод сервопривода |
| R02 | [Pololu: DRV8874 carrier](https://www.pololu.com/product/4035) | Режимы drive/brake/coast, входы и ограничения конкретной платы; не автоматическое одобрение любого аналога |
| R03 | [NiceNano documentation](https://nicekeyboards.com/docs/nice-nano/) | 21 GPIO оригинального изделия; не доказательство разводки клона |
| R04 | [NXP: PCA9685](https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf) | I²C PWM, общий генератор частоты, OE и состояния выходов; кандидат управления серво, не силовой драйвер двигателя |

Сообщение о заказе JGB37-520 и цветовая схема/таблица продавца предоставлены владельцем в разговоре. Это исходные сведения для проверки экземпляра, не результаты измерений и не независимый паспорт производителя.
