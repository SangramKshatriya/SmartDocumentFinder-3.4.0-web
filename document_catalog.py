"""Canonical document ontology used by local search and DigiLocker matching.

The static aliases are deliberately only a fallback. When DigiLocker is configured,
its issuer/document metadata can be discovered at runtime so the search surface can
cover the document types actually exposed to the registered requester.
"""
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class DocumentDefinition:
    key: str
    display_name: str
    aliases: Tuple[str, ...]


# Common DigiLocker-style document names plus useful local-file synonyms.
# The remote DigiLocker catalog remains the source of truth for the full issuer
# catalogue; this fallback makes search useful without a network connection.
DOCUMENTS: Tuple[DocumentDefinition, ...] = (
    DocumentDefinition("aadhaar", "Aadhaar Card", (
        "aadhaar", "aadhar", "aadhaar card", "aadhar card", "uidai", "uid",
        "आधार", "आधार कार्ड", "આધાર", "આધાર કાર્ડ", "ஆதார்", "ஆதார் அட்டை",
        "ఆధార్", "ಆಧಾರ್", "ആധാർ", "আধার", "ਆਧਾਰ", "ଆଧାର",  # harmless fallback token
    )),
    DocumentDefinition("pan", "PAN Card", (
        "pan", "pan card", "permanent account number", "pan verification record",
        "पैन", "पैन कार्ड", "पॅन", "पॅन कार्ड", "પાન", "પાન કાર્ડ", "பான்", "பான் அட்டை",
        "పాన్", "పాన్ కార్డు", "ಪ್ಯಾನ್", "ಪ್ಯಾನ್ ಕಾರ್ಡ್", "പാൻ", "প্যান", "ਪੈਨ", "ପାନ",
        "پین", "پین کارڈ",
    )),
    DocumentDefinition("marksheet", "Marksheet", (
        "marksheet", "mark sheet", "grade sheet", "result", "scorecard",
        "10th marksheet", "12th marksheet", "class 10 marksheet", "class 12 marksheet",
        "school marksheet", "college marksheet", "academic marksheet", "passing certificate",
        "मार्कशीट", "मार्क शीट", "अंकपत्र", "अंक तालिका", "रिजल्ट", "गुणपत्रिका", "निकाल",
        "માર્કશીટ", "ગુણપત્રક", "પરિણામ", "மார்க் ஷீட்", "மதிப்பெண்", "முடிவு",
        "మార్క్ షీట్", "ఫలితం", "ಅಂಕಪಟ್ಟಿ", "ಫಲಿತಾಂಶ", "മാർക്ക് ഷീറ്റ്", "ഫലം",
        "মার্কশিট", "নম্বরপত্র", "ফলাফল", "ਮਾਰਕਸ਼ੀਟ", "ਅੰਕਪੱਤਰ", "ଫଳାଫଳ",
    )),
    DocumentDefinition("driving_license", "Driving Licence", (
        "driving license", "driving licence", "driver license", "driver licence", "dl",
        "driving card", "लाइसेंस", "ड्राइविंग लाइसेंस", "ड्रायव्हिंग लायसन्स", "ड्रायव्हिंग परवाना",
        "ડ્રાઇવિંગ લાયસન્સ", "டிரைவிங் லைசென்ஸ்", "ஓட்டுநர் உரிமம்", "డ్రైవింగ్ లైసెన్స్",
        "ಡ್ರೈವಿಂಗ್ ಲೈಸೆನ್ಸ್", "ഡ്രൈവിംഗ് ലൈസൻസ്", "ড্রাইভিং লাইসেন্স", "ਡਰਾਈਵਿੰਗ ਲਾਇਸੈਂਸ",
        "ଡ୍ରାଇଭିଂ ଲାଇସେନ୍ସ", "ر ڈرائیونگ لائسنس",
    )),
    DocumentDefinition("rc", "Vehicle Registration Certificate", (
        "registration certificate", "vehicle registration", "vehicle registration certificate",
        "car registration", "bike registration", "rc book", "rc", "registration card",
        "वाहन पंजीकरण", "पंजीकरण प्रमाणपत्र", "आरसी", "वाहन नोंदणी", "नोंदणी प्रमाणपत्र",
        "વાહન નોંધણી", "નોંધણી પ્રમાણપત્ર", "வாகன பதிவு", "பதிவு சான்றிதழ்",
        "వాహన రిజిస్ట్రేషన్", "ఆర్సీ", "ವಾಹನ ನೋಂದಣಿ", "ನೋಂದಣಿ ಪ್ರಮಾಣಪತ್ರ",
        "വാഹന രജിസ്ട്രേഷൻ", "ആർസി", "যানবাহন নিবন্ধন", "ਵਾਹਨ ਰਜਿਸਟ੍ਰੇਸ਼ਨ", "ଯାନ ପଞ୍ଜୀକରଣ",
    )),
    DocumentDefinition("insurance", "Vehicle Insurance", (
        "insurance", "vehicle insurance", "car insurance", "bike insurance", "insurance paper",
        "insurance document", "बीमा", "इंश्योरेंस", "ବୀମା", "વીમા", "விமா", "భీమా", "ವಿಮೆ",
        "ഇൻഷുറൻസ്", "বীমা", "ਬੀਮਾ", "پالیسی", "insurance policy",
    )),
    DocumentDefinition("puc", "Pollution Under Control Certificate", (
        "puc", "puc certificate", "pollution certificate", "pollution paper", "pollution under control",
        "प्रदूषण प्रमाणपत्र", "पीयूसी", "पॉल्यूशन", "પ્રદૂષણ પ્રમાણપત્ર", "மாசுக் கட்டுப்பாட்டு சான்றிதழ்",
        "కాలుష్య ధృవపత్రం", "ಮಾಲಿನ್ಯ ಪ್ರಮಾಣಪತ್ರ", "മലിനീകരണ സർട്ടിഫിക്കറ്റ്", "দূষণ শংসাপত্র",
    )),
    DocumentDefinition("voter_id", "Voter ID", (
        "voter id", "voter card", "epic", "elector photo identity card",
        "मतदाता पहचान पत्र", "वोटर कार्ड", "મતદાર ઓળખપત્ર", "வாக்காளர் அட்டை", "ఓటర్ ఐడి",
        "ಮತದಾರರ ಗುರುತಿನ ಚೀಟಿ", "വോട്ടർ ഐഡി", "ভোটার আইডি", "ਵੋਟਰ ਕਾਰਡ", "ଭୋଟର ଆଇଡି",
    )),
    DocumentDefinition("passport", "Passport", (
        "passport", "पासपोर्ट", "पासपोर्ट दस्तावेज", "પાસપોર્ટ", "பாஸ்போர்ட்", "పాస్‌పోర్ట్",
        "ಪಾಸ್‌ಪೋರ್ಟ್", "പാസ്‌പോർട്ട്", "পাসপোর্ট", "ਪਾਸਪੋਰਟ", "ପାସପୋର୍ଟ", "پاسپورٹ",
    )),
    DocumentDefinition("birth_certificate", "Birth Certificate", (
        "birth certificate", "birth record", "जन्म प्रमाण पत्र", "जन्म प्रमाणपत्र", "जन्म दाखला",
        "જન્મ પ્રમાણપત્ર", "பிறப்பு சான்றிதழ்", "జనన ధృవీకరణ పత్రం", "ಜನನ ಪ್ರಮಾಣಪತ್ರ",
        "ജനന സർട്ടിഫിക്കറ്റ്", "জন্ম সনদ", "ਜਨਮ ਸਰਟੀਫਿਕੇਟ", "ଜନ୍ମ ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("death_certificate", "Death Certificate", (
        "death certificate", "death record", "मृत्यु प्रमाण पत्र", "मृत्यु प्रमाणपत्र",
        "મૃત્યુ પ્રમાણપત્ર", "இறப்பு சான்றிதழ்", "మరణ ధృవీకరణ పత్రం", "ಮರಣ ಪ್ರಮಾಣಪತ್ರ",
        "മരണ സർട്ടിഫിക്കറ്റ്", "মৃত্যু সনদ", "ਮੌਤ ਸਰਟੀਫਿਕੇਟ", "ମୃତ୍ୟୁ ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("marriage_certificate", "Marriage Certificate", (
        "marriage certificate", "विवाह प्रमाण पत्र", "विवाह प्रमाणपत्र", "લગ્ન પ્રમાણપત્ર",
        "திருமணச் சான்றிதழ்", "వివాహ ధృవీకరణ పత్రం", "ವಿವಾಹ ಪ್ರಮಾಣಪತ್ರ", "വിവാഹ സർട്ടിഫിക്കറ്റ്",
        "বিবাহ শংসাপত্র", "ਵਿਆਹ ਸਰਟੀਫਿਕੇਟ", "ବିବାହ ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("income_certificate", "Income Certificate", (
        "income certificate", "income proof", "आय प्रमाण पत्र", "आय प्रमाणपत्र", "उत्पन्न प्रमाणपत्र",
        "આવક પ્રમાણપત્ર", "வருமானச் சான்றிதழ்", "ఆదాయ ధృవీకరణ పత్రం", "ಆದಾಯ ಪ್ರಮಾಣಪತ್ರ",
        "വരുമാന സർട്ടിഫിക്കറ്റ്", "আয় শংসাপত্র", "ਆਮਦਨ ਸਰਟੀਫਿਕੇਟ", "ଆୟ ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("caste_certificate", "Caste Certificate", (
        "caste certificate", "जाति प्रमाण पत्र", "जाति प्रमाणपत्र", "जात प्रमाणपत्र",
        "જાતિ પ્રમાણપત્ર", "சாதிச் சான்றிதழ்", "కుల ధృవీకరణ పత్రం", "ಜಾತಿ ಪ್ರಮಾಣಪತ್ರ",
        "ജാതി സർട്ടിഫിക്കറ്റ്", "জাতিগত শংসাপত্র", "ਜਾਤੀ ਸਰਟੀਫਿਕੇਟ", "ଜାତି ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("domicile_certificate", "Domicile / Residence Certificate", (
        "domicile certificate", "residence certificate", "resident certificate", "address certificate",
        "निवास प्रमाण पत्र", "अधिवास प्रमाणपत्र", "મૂળ નિવાસ પ્રમાણપત્ર", "குடியிருப்பு சான்றிதழ்",
        "నివాస ధృవీకరణ పత్రం", "ನಿವಾಸ ಪ್ರಮಾಣಪತ್ರ", "താമസ സർട്ടിഫിക്കറ്റ്", "বাসস্থান শংসাপত্র",
        "ਰਿਹਾਇਸ਼ ਸਰਟੀਫਿਕੇਟ", "ନିବାସ ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("ews_certificate", "EWS Certificate", (
        "ews certificate", "economically weaker section certificate", "ews", "ईडब्ल्यूएस प्रमाण पत्र",
        "आर्थिक रूप से कमजोर वर्ग प्रमाणपत्र", "ઇડબલ્યુએસ પ્રમાણપત્ર", "EWS சான்றிதழ்", "EWS సర్టిఫికేట్",
        "EWS ಪ್ರಮಾಣಪತ್ರ", "EWS സർട്ടിഫിക്കറ്റ്", "EWS শংসাপত্র", "EWS ਸਰਟੀਫਿਕੇਟ", "EWS ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("disability_certificate", "Disability Certificate", (
        "disability certificate", "уд", "udid", "unique disability id", "विकलांगता प्रमाण पत्र",
        "दिव्यांग प्रमाणपत्र", "અપંગતા પ્રમાણપત્ર", "மாற்றுத்திறனாளி சான்றிதழ்", "వికలాంగత ధృవీకరణ పత్రం",
        "ಅಂಗವೈಕಲ್ಯ ಪ್ರಮಾಣಪತ್ರ", "വൈകല്യ സർട്ടിഫിക്കറ്റ്", "প্রতিবন্ধী শংসাপত্র", "ਅਪੰਗਤਾ ਸਰਟੀਫਿਕੇਟ",
        "ଦିବ୍ୟାଙ୍ଗ ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("ration_card", "Ration Card", (
        "ration card", "food security card", "राशन कार्ड", "રેશન કાર્ડ", "ரேஷன் கார்டு", "రేషన్ కార్డు",
        "ಪಡಿತರ ಚೀಟಿ", "റേഷൻ കാർഡ്", "রেশন কার্ড", "ਰਾਸ਼ਨ ਕਾਰਡ", "ରାସନ କାର୍ଡ",
    )),
    DocumentDefinition("degree_certificate", "Degree Certificate", (
        "degree certificate", "degree", "graduation certificate", "उपाधि प्रमाणपत्र", "डिग्री प्रमाणपत्र",
        "ડિગ્રી પ્રમાણપત્ર", "பட்டச் சான்றிதழ்", "డిగ్రీ సర్టిఫికేట్", "ಪದವಿ ಪ್ರಮಾಣಪತ್ರ",
        "ഡിഗ്രി സർട്ടിഫിക്കറ്റ്", "ডিগ্রি সার্টিফিকেট", "ਡਿਗਰੀ ਸਰਟੀਫਿਕੇਟ", "ଡିଗ୍ରୀ ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("diploma_certificate", "Diploma Certificate", (
        "diploma certificate", "diploma", "डिप्लोमा प्रमाणपत्र", "ડિપ્લોમા પ્રમાણપત્ર",
        "டிப்ளமா சான்றிதழ்", "డిప్లొమా సర్టిఫికేట్", "ಡಿಪ್ಲೊಮಾ ಪ್ರಮಾಣಪತ್ರ", "ഡിപ്ലോമ സർട്ടിഫിക്കറ്റ്",
        "ডিপ্লোমা সার্টিফিকেট", "ਡਿਪਲੋਮਾ ਸਰਟੀਫਿਕੇਟ", "ଡିପ୍ଲୋମା ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("migration_certificate", "Migration Certificate", (
        "migration certificate", "स्थानांतरण प्रमाणपत्र", "प्रवासन प्रमाणपत्र", "માઇગ્રેશન પ્રમાણપત્ર",
        "இடம்பெயர்வு சான்றிதழ்", "మైగ్రేషన్ సర్టిఫికేట్", "ಮೈಗ್ರೇಷನ್ ಪ್ರಮಾಣಪತ್ರ", "മൈഗ്രേഷൻ സർട്ടിഫിക്കറ്റ്",
        "মাইগ্রেশন সার্টিফিকেট", "ਮਾਈਗ੍ਰੇਸ਼ਨ ਸਰਟੀਫਿਕੇਟ", "ମାଇଗ୍ରେସନ ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("transfer_certificate", "Transfer Certificate", (
        "transfer certificate", "tc", "स्थानांतरण प्रमाण पत्र", "स्थानांतरण प्रमाणपत्र",
        "ટ્રાન્સફર સર્ટિફિકેટ", "மாற்றுச் சான்றிதழ்", "బదిలీ ధృవీకరణ పత్రం", "ವರ್ಗಾವಣೆ ಪ್ರಮಾಣಪತ್ರ",
        "ട്രാൻസ്ഫർ സർട്ടിഫിക്കറ്റ്", "স্থানান্তর শংসাপত্র", "ਟ੍ਰਾਂਸਫਰ ਸਰਟੀਫਿਕੇਟ", "ସ୍ଥାନାନ୍ତରଣ ପ୍ରମାଣପତ୍ର",
    )),
    DocumentDefinition("passbook", "Bank Passbook", (
        "bank passbook", "passbook", "bank book", "account passbook", "पासबुक", "बैंक पासबुक",
        "બેંક પાસબુક", "வங்கி பாஸ்புக்", "బ్యాంక్ పాస్‌బుక్", "ಬ್ಯಾಂಕ್ ಪಾಸ್‌ಬುಕ್", "ബാങ്ക് പാസ്‌ബുക്ക്",
        "ব্যাংক পাসবুক", "ਬੈਂਕ ਪਾਸਬੁੱਕ", "ବ୍ୟାଙ୍କ ପାସବୁକ୍",
    )),
    DocumentDefinition("fee_receipt", "Fee Receipt", (
        "fee receipt", "fees receipt", "tuition receipt", "शुल्क रसीद", "फीस रसीद", "फी पावती",
        "ફી રસીદ", "கட்டண ரசீது", "ఫీజు రసీదు", "ಶುಲ್ಕ ರಸೀದಿ", "ഫീസ് രസീത്", "ফি রসিদ",
        "ਫੀਸ ਰਸੀਦ", "ଫି ରସିଦ",
    )),
)

DOCUMENT_BY_KEY: Dict[str, DocumentDefinition] = {item.key: item for item in DOCUMENTS}


def iter_aliases():
    for item in DOCUMENTS:
        for alias in item.aliases:
            yield alias, item.key


def display_name(document_type: str) -> str:
    item = DOCUMENT_BY_KEY.get(document_type)
    return item.display_name if item else document_type.replace("_", " ").title()


def aliases_for(document_type: str) -> Tuple[str, ...]:
    item = DOCUMENT_BY_KEY.get(document_type)
    return item.aliases if item else ()
