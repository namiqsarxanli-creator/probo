# Autonomous Inc. — v0.2

**Yeni Research Studio üçün [README_STUDIO.md](README_STUDIO.md) sənədinə baxın.**

Yeni panel `main.py` ilə 8812 portunda açılır. Aşağıdakı bölmə əvvəlki v0.1 simulyatorunun arxiv sənədidir; onu `legacy.py` ilə 8811 portunda başladın.

## v0.1 — arxiv

Öz komandasını quran şirkət üçün işlək lokal simulyator. Python 3.10+ standart kitabxanası ilə işləyir; paket və API açarı tələb olunmur.

## Başlatmaq

PyCharm-da bu qovluğu açın, Python 3.10+ interpreter seçin və `main.py` faylını Run edin.

```powershell
python main.py
```

Brauzer: http://127.0.0.1:8810

Portu dəyişmək üçün `PORT` mühit dəyişənindən istifadə edin. Server yalnız lokal interfeysə bağlanır. İnternetə açmaq üçün nəzərdə tutulmayıb.

## Nümayiş

1. Məqsəd və 20 kredit büdcə ilə şirkəti başladın.
2. Rəhbər plan qurur, üç nümunə namizəd arasından mütəxəssis seçir.
3. İlk işçi 1/4 və ya 2/4 mərhələsinə çatanda onu işdən çıxarın.
4. Əvəzləyici işə qəbul olunur, təhvil paketini qəbul edib saxlanılmış mərhələdən davam edir.
5. Büdcəni sərf edilmiş məbləğə yaxınlaşdırıb büdcə blokunu sınayın. Sonra büdcəni artırıb Davam et düyməsini basın.
6. İş axını bitəndə simulyasiya hesabatını yükləyin.

Hər 3 saniyədə bir qərar və ya iş addımı icra olunur. Normal axın təxminən 70 saniyə çəkir. Fasilə düyməsi ilə prosesi saxlamaq olar. SQLite vəziyyəti server yenidən başladıqda bərpa edir. İlk versiya bir şirkət saxlayır, interfeysdə tarixçəni silən əməliyyat yoxdur.

## Nə gerçəkdir, nə simulyasiyadır?

Gerçək proqram məntiqi: SQLite tranzaksiyaları, iş asılılıqları, büdcə limiti, işçinin deaktivləşdirilməsi, təhvil, davam etmə və vəziyyətin saxlanması.

Simulyasiya: namizədlərin balları, agent qərarlarının məzmunu və tapşırıq nəticələri. LLM, internet araşdırması, real maliyyə və xarici mesaj göndərilməsi yoxdur. Kreditlər real dollar deyil. Hesabat araşdırma nəticəsi deyil, iş axınının nümayişidir.

İşə qəbul: 0.20 kredit; iş mərhələsi: 0.15 kredit. Dəyişikliksiz tam axın: 3.20 kredit. Aktiv işçi limiti rəhbər daxil 5 nəfərdir. Bu versiya rolları sabit şablondan götürür və yalnız ehtiyac yarandıqda işçi yaradır. Avtonom işdən çıxarma, dinamik rol yaratma və real sınaq tapşırığının qiymətləndirilməsi növbəti mərhələdir.

## Testlər

```powershell
python -m unittest discover -s tests -v
```

## Struktur

- `app/engine.py`: şirkətin vəziyyət maşını, büdcə, işə qəbul və təhvil.
- `app/server.py`: lokal HTTP API və fon planlayıcısı.
- `static/`: Azərbaycan dilində idarəetmə paneli.
- `tests/`: davamlılıq, büdcə, təhvil və asılılıqlar üçün testlər.
- `data/company.sqlite3`: avtomatik yaranan iş məlumatları.

## Növbəti mərhələ

LLM provayder interfeysi, real sınaq tapşırıqları, mənbəli araşdırma aləti, ölçülən keyfiyyətə əsaslanan əvəzləmə qərarı və sabit komanda ilə müqayisə. Xarici əməliyyatlar üçün icazə və xərc nəzarəti icra qatında saxlanmalıdır.
