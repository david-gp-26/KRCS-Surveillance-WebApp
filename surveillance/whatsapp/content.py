"""All WhatsApp wording, in English and Kiswahili.

The reporter picks the language in the chat, so the text lives here rather than in Frappe translations.
WhatsApp limits: button titles <= 20 characters, list row titles <= 24, row descriptions <= 72
(checked on every message by test_conversation.py).
First-aid text is copied from the demo and must be confirmed by KRCS. ADVICE is a draft from standard
WHO / MoH community messages, pending sign-off by the KRCS Public Health Specialist and a Kiswahili reviewer.
"""
# The en dashes are intended: they are shown to WhatsApp users.
# ruff: noqa: RUF001

HOTLINE = "1199"

CONTACT = {
	"phone": "(+254) 703 037 000",
	"emails": ["info@redcross.or.ke", "communications@redcross.or.ke"],
	"office": "South C (Bellevue), Red Cross Road, off Popo Road, Nairobi, Kenya",
}

# Keywords that work at any point in the conversation.
KEYWORDS = {
	"greeting": {"hi", "hello", "hey", "start", "habari", "jambo", "mambo", "sasa"},
	"menu": {"menu", "main menu", "menyu", "menyu kuu"},
	"help": {"help", "msaada", "hotline"},
	"cancel": {"cancel", "stop", "ghairi", "acha"},
	"language": {"language", "lugha"},
	"back": {"back", "rudi"},
	"emergency": {"emergency", "emergencies", "dharura"},  # anywhere in a message, not only on its own
	"privacy": {"privacy", "faragha"},
}

# Draft for approval by the KRCS Data Protection Officer, from the DPIA review. Change the version when the wording
# changes in substance: everyone is then asked again, and the WhatsApp Consent Log shows which text each person saw.
PRIVACY_VERSION = "2026-11-draft"
PRIVACY_NOTICE = f"""*Your privacy / Faragha yako*

Kenya Red Cross collects what you send here to detect and respond to disease outbreaks. Your number, name and report are stored in Kenya and seen only by authorised KRCS staff. WhatsApp (Meta) carries these messages and processes them outside Kenya. Type *PRIVACY* at any time for your rights, or call *{HOTLINE}*.

Kenya Red Cross hukusanya unachotuma hapa ili kugundua na kukabili milipuko ya magonjwa. Nambari, jina na taarifa yako huhifadhiwa Kenya na huonekana kwa wafanyakazi wa KRCS walioidhinishwa pekee. WhatsApp (Meta) hubeba ujumbe huu na kuuchakata nje ya Kenya. Andika *FARAGHA* wakati wowote kujua haki zako, au piga *{HOTLINE}*.

Do you agree? / Je, unakubali?"""
PRIVACY_DECLINED = f"""We have not taken a report. You can still report by calling *{HOTLINE}* _(free)_ or by telling your Community Health Promoter. If someone's life is in danger, call *999* or *112*.

Hatujapokea taarifa. Bado unaweza kuripoti kwa kupiga *{HOTLINE}* _(bure)_ au kumwambia Mhudumu wako wa Afya ya Jamii. Ikiwa maisha ya mtu yako hatarini, piga *999* au *112*."""

HELP_EN = f"""*KRCS Surveillance Support & Hotlines*

Toll-free helpline: *{HOTLINE}* _(free)_
Life-threatening emergency: *999* or *112*

*Kenya Red Cross Society*
Phone: {CONTACT["phone"]}
Email: {" · ".join(CONTACT["emails"])}
Office: {CONTACT["office"]}

Words you can type at any time:
• *menu* – main menu
• *cancel* – stop the current report
• *language* – change language"""

HELP_SW = f"""*Msaada wa KRCS na Nambari za Dharura*

Nambari ya bure: *{HOTLINE}* _(bure)_
Dharura ya kuhatarisha maisha: *999* au *112*

*Kenya Red Cross Society*
Simu: {CONTACT["phone"]}
Barua pepe: {" · ".join(CONTACT["emails"])}
Ofisi: {CONTACT["office"]}

Maneno unayoweza kuandika wakati wowote:
• *menyu* – menyu kuu
• *ghairi* – kusimamisha taarifa
• *lugha* – kubadilisha lugha"""

HEALTH_TIPS = f"""*KRCS Mwongozo wa Afya na Huduma ya Kwanza / First Aid Guidance*

• *Kuharisha na Kutapika / Diarrhea & Vomiting:* Kunywa ORS mara kwa mara kwenye maji safi ya kuchemsha.
• *Maji Safi ya Kunywa / Clean Water:* Chemsha maji au tumia dawa ya kutibu maji kabla ya kunywa.
• *Homa Kali / High Fever:* Mpe mgonjwa maji mengi na umpeleke kituo cha afya kilicho karibu mara moja.
• *Ugonjwa wa Mifugo / Sick Animals:* USICHINJE wala kula nyama ya mnyama mgonjwa au aliyekufa.

*Hotline ya Dharura: {HOTLINE}*"""

CHOOSE_LANGUAGE = """*Karibu Kenya Red Cross Society / Welcome to Kenya Red Cross*

Tafadhali chagua lugha unayopendelea kutoa taarifa ya afya:
Please choose your preferred language to report:"""

# Friendly labels for Case Report select values. Unknown values (added later in Frappe) show as-is.
LABELS = {
	"en": {
		"category": {
			"Human Disease": "Human disease",
			"Animal Disease": "Animal disease",
			"All Disease": "Human and animal",
		},
		"age_group": {
			"Under 1": "Under 1 year",
			"1-4 years": "1–4 years",
			"5-14 years": "5–14 years",
			"15+ years": "15 years and over",
		},
		"animal_exposure": {
			"None": "No",
			"Bite or scratch": "Bitten or scratched",
			"Handled sick or dead animal": "Handled sick/dead animal",
		},
		"status": {
			"Submitted": "Submitted",
			"Reviewed": "Reviewed",
			"Linked": "Linked to an alert",
			"Investigating": "Under investigation",
			"Closed": "Closed",
		},
		# Symptom.category, shown in everyday words. Frappe keeps the clinical name.
		"symptom_group": {
			"Gastrointestinal": "Stomach & diarrhoea",
			"Respiratory": "Breathing & chest",
			"Dermatological": "Skin & swelling",
			"Febrile/Systemic": "Fever & body pain",
			"Neurological": "Stiff neck & confusion",
			"Haemorrhagic": "Bleeding",
		},
	},
	"sw": {
		"category": {
			"Human Disease": "Ugonjwa wa binadamu",
			"Animal Disease": "Ugonjwa wa wanyama",
			"All Disease": "Binadamu na wanyama",
		},
		"age_group": {
			"Under 1": "Chini ya mwaka 1",
			"1-4 years": "Miaka 1–4",
			"5-14 years": "Miaka 5–14",
			"15+ years": "Miaka 15 na zaidi",
		},
		"animal_exposure": {
			"None": "Hapana",
			"Bite or scratch": "Aliumwa au kukwaruzwa",
			"Handled sick or dead animal": "Alishika mnyama mgonjwa",
		},
		"status": {
			"Submitted": "Imepokelewa",
			"Reviewed": "Imekaguliwa",
			"Linked": "Imeunganishwa na tahadhari",
			"Investigating": "Inachunguzwa",
			"Closed": "Imefungwa",
		},
		"symptom_group": {
			"Gastrointestinal": "Tumbo na kuhara",
			"Respiratory": "Kupumua na kifua",
			"Dermatological": "Ngozi na uvimbe",
			"Febrile/Systemic": "Homa na maumivu",
			"Neurological": "Shingo ngumu na fahamu",
			"Haemorrhagic": "Kutokwa na damu",
		},
	},
}


def label(lang, field, value):
	return LABELS.get(lang, {}).get(field, {}).get(value) or LABELS["en"].get(field, {}).get(value) or value


# Symptoms are matched by name without any "(…)" part, lower-case: "Fever (hot body)" -> "fever".
# Shown first, in this order, so most reporters never need the groups. Names not in Frappe are skipped.
COMMON_SYMPTOMS = [
	"fever",
	"diarrhea",
	"vomiting",
	"cough",
	"difficulty breathing",
	"rash",
	"unexplained bleeding",
	"headache",
]

# Everyday English and Kiswahili words for a symptom, found anywhere in a typed message.
# To be reviewed by KRCS.
SYMPTOM_WORDS = {
	"fever": ["hot body", "high temperature", "temperature", "homa", "joto", "mwili moto", "joto mwilini"],
	"chills": ["shivering", "baridi", "kutetemeka", "kutetemeka kwa baridi"],
	"headache": ["head ache", "head pain", "maumivu ya kichwa", "kichwa kuuma", "kuumwa na kichwa"],
	"fatigue": ["tired", "tiredness", "weakness", "uchovu", "kuchoka", "udhaifu"],
	"joint pain": ["painful joints", "maumivu ya viungo", "viungo kuuma"],
	"severe body or muscle pain": [
		"body pain",
		"body ache",
		"muscle pain",
		"maumivu ya mwili",
		"maumivu ya misuli",
		"mwili kuuma",
	],
	"red eyes": ["eyes red", "macho mekundu"],
	"yellow eyes or skin": ["yellow eyes", "yellow skin", "jaundice", "macho ya njano", "manjano"],
	"swollen lymph nodes": ["swollen glands", "tezi", "tezi kuvimba"],
	"diarrhea": [
		"diarrhoea",
		"running stomach",
		"loose stool",
		"loose stools",
		"watery stool",
		"kuhara",
		"kuharisha",
		"anaharisha",
		"wanaharisha",
		"kuendesha",
		"tumbo la kuhara",
	],
	"vomiting": ["vomit", "vomits", "vomited", "throwing up", "kutapika", "anatapika", "wanatapika"],
	"abdominal pain": [
		"stomach pain",
		"stomach ache",
		"stomachache",
		"tummy pain",
		"maumivu ya tumbo",
		"tumbo kuuma",
		"kuumwa na tumbo",
	],
	"dehydration": ["upungufu wa maji", "upungufu wa maji mwilini"],
	"bloody stool": ["blood in stool", "damu kwenye choo", "choo cha damu", "kuhara damu"],
	"cough": ["coughing", "kikohozi", "kukohoa", "anakohoa", "wanakohoa"],
	"difficulty breathing": [
		"short of breath",
		"shortness of breath",
		"breathing difficulty",
		"cannot breathe",
		"kupumua kwa shida",
		"shida ya kupumua",
		"kukosa pumzi",
	],
	"chest pain": ["maumivu ya kifua", "kifua kuuma"],
	"runny nose": ["mafua", "kamasi"],
	"rash": ["spots", "upele", "vipele"],
	"itching": ["itchy", "itch", "kuwashwa", "mwasho"],
	"skin lesions": ["skin wounds", "sores", "vidonda", "vidonda vya ngozi"],
	"black skin sore": ["black sore", "kidonda cheusi"],
	"swelling": ["swollen", "uvimbe", "kuvimba"],
	"unexplained bleeding": ["bleeding", "kutokwa na damu", "kutoka damu"],
	"stiff neck": ["neck stiff", "shingo ngumu", "shingo kukakamaa"],
	"confusion or unconsciousness": [
		"confused",
		"confusion",
		"unconscious",
		"fainting",
		"fainted",
		"kuchanganyikiwa",
		"kupoteza fahamu",
		"kuzimia",
	],
	"sudden weakness of arm or leg": [
		"weak arm",
		"weak leg",
		"paralysis",
		"cannot walk",
		"kupooza",
		"udhaifu wa mkono",
		"udhaifu wa mguu",
	],
	"bulging soft spot": ["bulging fontanelle", "utosi kuvimba"],
}

# Words that cancel the symptom named right after them ("no fever", "hakuna homa").
NEGATIONS = {"no", "not", "without", "hakuna", "bila", "hana", "sina"}


def _step_en(n, total, title):
	"""n is None for a question asked outside the numbered steps (a follow-up the reporter chose to edit)."""
	return f"*Step {n} of {total}: {title}*" if n else f"*{title}*"


def _step_sw(n, total, title):
	return f"*Hatua {n} kati ya {total}: {title}*" if n else f"*{title}*"


# What to do while waiting, by Symptom.category, shown after a community report (SRS R10) and, for danger signs,
# straight after the description. DRAFT: to be approved by the KRCS Public Health Specialist. An Approved
# Community Advice record with the same key (and language) replaces the text here; see data.community_advice.
ADVICE = {
	"en": {
		"title": "*While you wait for the KRCS team*",
		"Gastrointestinal": "*Diarrhoea or vomiting:* give ORS (oral rehydration salts) often, in small sips, and keep breastfeeding babies. Wash hands with soap after the toilet and before handling food. Drink only boiled or treated water. Go to a health facility at once if the person cannot drink, is very weak or has blood in the stool.",
		"Respiratory": "*Cough or breathing problems:* cover coughs and sneezes, and keep the sick person in a well-aired room, away from others where possible. Go to a health facility at once if breathing is fast or difficult.",
		"Febrile/Systemic": "*Fever:* give plenty of fluids and go to a health facility to be tested; fever can be malaria. Sleep under a treated mosquito net.",
		"Dermatological": "*Rash or skin sores:* keep the sick person away from others where possible, and do not share towels, clothes or bedding. Go to a health facility.",
		"Neurological": "*Stiff neck, confusion, fits or sudden weakness:* this needs urgent care. Take the person to a health facility now.",
		"Haemorrhagic": "*Bleeding:* take the person to a health facility now. Do not touch blood or body fluids with bare hands. If someone has died, do not wash or touch the body; wait for the health team.",
		"animals": "*Sick or dead animals:* do not slaughter, eat, sell or touch sick or dead animals, their meat or their milk. Keep sick animals apart and tell the local veterinary officer.",
		"bite": "*Animal bite or scratch:* wash the wound with soap and running water for 15 minutes, and go to a health facility today.",
		"general": "*If the person gets worse* (cannot drink, very weak, confused, bleeding or struggling to breathe), go to the nearest health facility at once.",
		"close": f"KRCS toll-free: *{HOTLINE}*. Emergency: *999* / *112*.",
	},
	"sw": {
		"title": "*Wakati unasubiri timu ya KRCS*",
		"Gastrointestinal": "*Kuhara au kutapika:* mpe ORS mara kwa mara, kidogo kidogo, na endelea kunyonyesha watoto wachanga. Nawa mikono kwa sabuni baada ya choo na kabla ya kushika chakula. Kunywa maji yaliyochemshwa au kutibiwa tu. Nenda kituo cha afya mara moja kama mgonjwa hawezi kunywa, ni dhaifu sana au ana damu kwenye choo.",
		"Respiratory": "*Kikohozi au shida ya kupumua:* funika mdomo unapokohoa au kupiga chafya, na mweke mgonjwa kwenye chumba chenye hewa, mbali na wengine inapowezekana. Nenda kituo cha afya mara moja kama anapumua haraka au kwa shida.",
		"Febrile/Systemic": "*Homa:* mpe maji mengi ya kunywa na mpeleke kituo cha afya akapimwe; homa inaweza kuwa malaria. Lala ndani ya chandarua kilichotibiwa.",
		"Dermatological": "*Upele au vidonda vya ngozi:* mweke mgonjwa mbali na wengine inapowezekana, na msishiriki taulo, nguo au matandiko. Nenda kituo cha afya.",
		"Neurological": "*Shingo ngumu, kuchanganyikiwa, degedege au udhaifu wa ghafla:* hii ni dharura. Mpeleke mgonjwa kituo cha afya sasa hivi.",
		"Haemorrhagic": "*Kutokwa na damu:* mpeleke mgonjwa kituo cha afya sasa hivi. Usiguse damu au majimaji ya mwili kwa mikono mitupu. Kama mtu amefariki, usiuoshe wala kuugusa mwili; subiri timu ya afya.",
		"animals": "*Wanyama wagonjwa au waliokufa:* usichinje, usile, usiuze wala kugusa wanyama wagonjwa au waliokufa, nyama yao au maziwa yao. Watenge wanyama wagonjwa na umjulishe afisa wa mifugo.",
		"bite": "*Kuumwa au kukwaruzwa na mnyama:* osha jeraha kwa sabuni na maji yanayotiririka kwa dakika 15, na uende kituo cha afya leo.",
		"general": "*Hali ya mgonjwa ikizidi kuwa mbaya* (hawezi kunywa, ni dhaifu sana, amechanganyikiwa, anatokwa na damu au anapumua kwa shida), nenda kituo cha afya kilicho karibu mara moja.",
		"close": f"Nambari ya bure ya KRCS: *{HOTLINE}*. Dharura: *999* / *112*.",
	},
}


# What a staff reporter sees after submitting: the same as the mobile app's "Next steps" (src/frappe/advice.ts,
# features/field/NextSteps.tsx). The protocol steps come from Frappe; these are the app's general lines.
NEXT_STEPS = {
	"en": {
		"title": "*Next steps*",
		"disease": lambda d: f"Suspected disease: *{d}*",
		"steps": lambda d: f"*What to do for {d or 'this report'}*",
		"also": "*Also*",
		"next": "*What happens next*",
		"general": [
			"Keep your phone on. A surveillance officer may call you to check this report.",
			"If anyone is very sick, help them get to the nearest health facility.",
			"Report any new cases or deaths you see, even if they look the same.",
		],
	},
	"sw": {
		"title": "*Hatua zinazofuata*",
		"disease": lambda d: f"Ugonjwa unaoshukiwa: *{d}*",
		"steps": lambda d: f"*Cha kufanya kwa {d or 'taarifa hii'}*",
		"also": "*Pia*",
		"next": "*Kinachofuata*",
		"general": [
			"Weka simu yako wazi. Afisa wa ufuatiliaji anaweza kukupigia kuthibitisha taarifa hii.",
			"Kama mtu ni mgonjwa sana, msaidie kufika kituo cha afya kilicho karibu.",
			"Ripoti visa vipya au vifo unavyoona, hata kama vinafanana.",
		],
	},
}


def _noted_en(items, left):
	head = f"*Thank you. From your message I noted:*\n{items}" if items else "*Thank you.*"
	tail = (
		("One more question" if left == 1 else f"{left} more questions") + " to complete the report."
		if left
		else "Please check the report below."
	)
	return f"{head}\n\n{tail}"


def _noted_sw(items, left):
	head = f"*Asante. Kutoka kwa ujumbe wako nimeandika:*\n{items}" if items else "*Asante.*"
	tail = (
		("Swali moja zaidi" if left == 1 else f"Maswali {left} zaidi") + " kukamilisha taarifa."
		if left
		else "Tafadhali kagua taarifa hapa chini."
	)
	return f"{head}\n\n{tail}"


def _who_en(who):
	return "animals" if who == "animals" else "people or animals" if who == "both" else "people"


def _staff_en(st, phone):
	role = f"\nRole: *{st['role']}*" if st.get("role") else ""
	region = f"\nRegion: *{st['region_label']}*" if st.get("region_label") else ""
	return (
		f"*WhatsApp number detected:* `{phone}`\n*Identity verified*\n\n"
		f"Welcome back, *{st['full_name']}*!{role}{region}\n\nHow can I help you today?"
	)


def _staff_sw(st, phone):
	role = f"\nWadhifa: *{st['role']}*" if st.get("role") else ""
	region = f"\nEneo: *{st['region_label']}*" if st.get("region_label") else ""
	return (
		f"*Nambari ya WhatsApp imetambuliwa:* `{phone}`\n*Utambulisho umethibitishwa*\n\n"
		f"Karibu tena, *{st['full_name']}*!{role}{region}\n\nNikusaidie vipi leo?"
	)


def _chosen(prefix, chosen):
	return f"{prefix}: {chosen}\n\n" if chosen else ""


T = {
	"en": {
		"help": HELP_EN,
		"invalid": "Sorry, I didn't understand that. Please choose one of the options, or type *menu*.",
		"emergency": f"If someone's life is in danger, call *999* or *112* now. KRCS toll-free: *{HOTLINE}* _(free, 24 hours)_.",
		"errorGeneric": f"Sorry, something went wrong on our side. Type *menu* to start again, or call *{HOTLINE}*.",
		"welcome": "*Welcome to Kenya Red Cross Society*\n\nI'm the KRCS Health Surveillance & Community Alert Assistant.\n\n"
		"_Serving both authorised health workers and community members across Kenya._\n\nPlease choose an option:",
		"roleCommunity": "Community member",
		"roleStaff": "KRCS Staff / CHP",
		"roleHelp": "Help & hotlines",
		"notStaff": lambda phone: f"This WhatsApp number (*{phone}*) is not linked to an active KRCS staff account.\n\n"
		"Ask your supervisor to add it as the *Mobile No* on your KRCS user profile, or continue as a community member.",
		"back": "Back",
		"staffVerified": _staff_en,
		"portal": "*KRCS Health Surveillance Portal*\n\nSelect an option below to proceed:",
		"menuReport": "Submit health report",
		"menuStatus": "Check report status",
		"menuRecent": "My recent reports",
		"menuHelp": "Help & support",
		"submitReport": "Submit a report",
		"backToMenu": "Main menu",
		# Response Support Chatbot. Answers are the service's own text (approved protocols or fixed templates).
		"menuAsk": "Ask a question",
		"askPrompt": "*Ask a question*\nType your question, e.g. _What should I do if I suspect cholera?_\n\n"
		"Answers come only from approved KRCS guidance. Type *menu* to go back.",
		"askPromptCommunity": "*Ask a question*\nType your question. If there is no approved answer, it is passed to the KRCS team.\n\n"
		"For an emergency call *999* or *112*. Type *menu* to go back.",
		"askClarify": "Which of these did you mean? Choose one, or type your question again.",
		"askRouted": "This sounds like a report of people who are sick. Please send it as a report so the surveillance team receives it.",
		"askMixed": "If people are sick now, please also send a report.",
		"askCount": "Report counts are not available on WhatsApp. Please use the *Reports* page of the KRCS surveillance app.",
		"askTeam": "the KRCS surveillance team",
		# Fixed reply when the service cannot be reached (frappe_interface.md §3).
		"askUnavailable": lambda contact: f"The guidance service is not available right now, so I have not answered. Your question has been passed to {contact}. "
		"If this is an emergency, follow your usual emergency reporting procedure.",
		"statusTitle": "*Your report status*",
		"recentTitle": "*Your recent reports*",
		"mineEmpty": "You have not sent any reports yet.",
		"mineHint": "_Send a reference (e.g. RPT-012) to see one report._",
		"submitNew": "Submit a new report",
		"refNotFound": lambda ref: f"No report *{ref}* was found among your reports.",
		"resume": "*You have an unfinished report.*\nWould you like to continue where you left off?",
		"paused": lambda minutes: f"*Session paused*\n\nYour session was paused after {minutes} minutes of inactivity. "
		"Your unfinished report has been kept as a draft.\n\nWould you like to continue where you left off?",
		"resumeBtn": "Continue",
		"restartBtn": "Start over",
		"cancelled": "*Report discarded*\n\nYour draft report has been cancelled. Nothing was sent.",
		"media": {"image": "Photo", "document": "Document", "audio": "Voice note", "video": "Video"},
		"mediaAdded": lambda what, n: f"*{what} attached*\n\nSupporting items attached: *{n}*",
		"mediaRefused": "That file type cannot be added to a report. Please send a photo, video, voice note or PDF.",
		"mediaNotSaved": lambda ref, n: f"Report *{ref}* was saved, but {n} attached file(s) could not be added. Each file must be 10 MB or smaller.",
		"moreOrReview": "_You can add more photos, files or voice notes, or tap *Proceed to review*._",
		"skip": "Skip",
		"more": "More",
		"prev": "Previous",
		"listButton": "Choose",
		"name": lambda n, t, profile: f"{_step_en(n, t, 'Your name')}\nWhat is your name?"
		+ ("\n\nTap the button if this is correct, or type your name." if profile else "\n\nType your name."),
		"nameInvalid": "Please type your name (at least 2 letters).",
		"category": lambda n,
		t: f"{_step_en(n, t, 'Signal category')}\nSelect the category of the public health signal or event:",
		"signal": lambda n,
		t: f"{_step_en(n, t, 'Signal type')}\nWhat type of health event are you reporting?",
		"symptomCommon": lambda n,
		t,
		chosen: f"{_step_en(n, t, 'What are you reporting?')}\n{_chosen('Selected', chosen)}"
		"Choose a symptom you see. You can choose more than one.\n\n"
		"Not in the list? Choose *Other symptoms*, or type what you see in your own words, e.g. _fever and diarrhoea_.",
		"symptomOther": "Other symptoms",
		"symptomOtherDesc": "All symptoms, by kind of problem",
		"symptomCommonBack": "Common symptoms",
		"symptomGroup": lambda n,
		t,
		chosen: f"{_step_en(n, t, 'What are you reporting?')}\n{_chosen('Selected', chosen)}"
		"What kind of problem is it? Each option shows examples.",
		"symptom": lambda group: f"*{group}*\nChoose the symptom you see, or type its name.",
		"symptomAll": lambda n,
		t,
		chosen: f"{_step_en(n, t, 'What are you reporting?')}\n{_chosen('Selected', chosen)}"
		"Choose a symptom you see, or type its name. You can choose more than one.",
		"symptomBack": "Other groups",
		"symptomNotFound": "I couldn't match that to a symptom. Choose from the list, or describe it in simple words, e.g. _fever_, _cough_, _diarrhoea_.",
		"symptomsMore": lambda items: f"*Selected symptoms:*\n{items}\n\nAdd another symptom, or continue?",
		"symptomsAdd": "Add another",
		"symptomsDone": "Continue",
		"symptomsClear": "Clear",
		"count": lambda n, t, who: f"{_step_en(n, t, f'Number of {_who_en(who)} affected')}\nHow many "
		+ (
			"animals are"
			if who == "animals"
			else "people or animals are"
			if who == "both"
			else "individuals are"
		)
		+ " presenting with these symptoms? Tap *Just one*, or type the number, e.g. 10.",
		"countOne": "Just one",
		"countInvalid": "*Invalid number*\n\nPlease enter a whole number from 1 to 100000.\n\nExample: `10`",
		"age": lambda n,
		t: f"{_step_en(n, t, 'Age group')} _(optional)_\nWhat is the age of the sick person(s)?",
		"exposure": lambda n, t: f"{_step_en(n, t, 'Contact with animals')} _(optional)_\n"
		"Was the sick person bitten or scratched by an animal, or did they handle a sick or dead animal?",
		"deaths": lambda n,
		t: f"{_step_en(n, t, 'Deaths')}\nHas anyone died? Type the number of deaths, or tap *None*.",
		"deathsNone": "None",
		"deathsInvalid": "Please type the number of deaths (0 or more), or tap *None*.",
		"region": lambda n, t: f"{_step_en(n, t, 'Where is it happening?')}\nSelect the region:",
		"regionYours": "Your assigned region",
		"subCounty": lambda n, t, region: f"{_step_en(n, t, 'Sub-county')}\nWhich sub-county of *{region}*?",
		"place": lambda n,
		t: f"{_step_en(n, t, 'Exact location')} _(optional)_\nShare your location, type the village, camp block or landmark, or skip.",
		"placeGps": "Use my location",
		"placeGpsPrompt": "Tap *Send location* to share where this is happening.\n\n_Or type the place name instead, or *skip*._",
		"placeRequired": lambda n,
		t: f"{_step_en(n, t, 'Exact location')}\nTap *Send location* and share where this is happening. "
		"You can send where you are now, or search for the place or pick it on the map.",
		"placePinPrompt": "Tap *Send location* and share the place on the map.",
		"placeNeedPin": lambda name: f"Noted: *{name}*.\nThe map location is also needed.",
		"placeName": "Please type the name of the place: village, camp block or landmark.",
		"placeNoSkip": "The location is needed for this report. Tap *Send location* above, or type the place name.",
		"placeReceived": lambda coords, name, area=None: f"*Location received*\n\nCoordinates: `{coords}`"
		+ (f"\nArea: *{name}*" if name else "")
		+ (f"\nSub-county and region: *{area}* (you can change them at review)" if area else ""),
		"onset": lambda n,
		t: f"{_step_en(n, t, 'When did it start?')}\nWhen were the first symptoms noticed?",
		"onsetToday": "Today",
		"onsetYesterday": "Yesterday",
		"onsetOther": "Specific date",
		"onsetDate": "Type the date the first symptoms were noticed, as *DD/MM/YYYY* (e.g. 28/09/2026).",
		"onsetInvalid": "That date is not valid. Use *DD/MM/YYYY*, not in the future and within the last 12 months.",
		"extra": lambda n, t, count: f"{_step_en(n, t, 'Supporting information')} _(optional)_\n"
		"Attach any photos, lab results, documents or voice notes, or type extra notes. You can send several."
		+ (
			f"\n\n_{count} item(s) attached so far._\n\nWhen finished, tap *Proceed to review*."
			if count
			else "\n\nNothing to add? Tap *Skip & review*."
		),
		"extraReview": "Proceed to review",
		"extraSkip": "Skip & review",
		"stepFooter": "Type back for the previous step, cancel to stop",
		"noteAdded": lambda note, n: f'*Text note added:*\n_"{note}"_\n\nSupporting items attached: *{n}*',
		# Free-text reporting (community members): describe in your own words, then only the missing questions.
		"describe": "*Tell us what is happening*\nIn your own words: who is sick, what signs you see, how many people or animals, "
		"where, and since when.\n\n_Example: 5 children in Ifo camp, Dadaab have had diarrhoea and vomiting since yesterday._\n\n"
		"Type in English or Kiswahili. Prefer to answer one question at a time? Tap *Step by step*.",
		"describeGuided": "Step by step",
		"describeMedia": "Photo saved with your report. Please also type a short description of what is happening, or tap *Step by step*.",
		"describeVoice": "Voice note saved with your report. It could not be read automatically, so please also type a short "
		"description, or tap *Step by step*.",
		"heard": lambda words: f'*From your voice note:*\n_"{words}"_\n\nPlease check the answers below, as the words may not be exact.',
		"clinicalBoundary": "I can't confirm what illness someone has, or advise on medicines or doses. A health worker needs to examine "
		"the person, so please take them to the nearest health facility.",
		"privacyFull": "*Your privacy*\n\n*Who:* Kenya Red Cross Society is responsible for your information. "
		f"Phone {CONTACT['phone']}, {CONTACT['emails'][0]}, {CONTACT['office']}.\n\n"
		"*Why:* to detect and respond to disease outbreaks.\n\n"
		"*Who sees it:* authorised KRCS health staff, who may share what is needed with the Ministry of Health. WhatsApp (Meta) "
		"carries these messages and processes them outside Kenya. KRCS's own systems, in Kenya, read your words to fill in your "
		"report and answer your questions.\n\n"
		"*Your rights:* you can ask to see, correct or delete your information, object to its use, or withdraw your agreement at "
		f"any time, here or by calling *{HOTLINE}*. A Community Health Promoter can do this with you.\n\n"
		"*Complaints:* contact KRCS, or the Office of the Data Protection Commissioner.\n\n"
		"Please do not send photos or recordings of people without their permission.",
		"privacyAsk": "What would you like to do?",
		"privacyWithdraw": "Withdraw agreement",
		"privacyRequest": "See or delete data",
		"privacyWithdrawn": "Your agreement is withdrawn and any unfinished report has been deleted. We will not take reports from "
		f"this number unless you agree again. To have reports you already sent deleted, type *PRIVACY* or call *{HOTLINE}*.",
		"privacyRequested": "Your request has been passed to the KRCS team, who will contact you on this number.",
		"describeLocation": "Location saved. Now type a short description of what is happening, or tap *Step by step*.",
		"noted": _noted_en,
		"urgent": "*This may be serious.* If anyone is very sick, unconscious, bleeding or struggling to breathe, take them to the "
		f"nearest health facility now or call *999* / *112*. KRCS toll-free: *{HOTLINE}*.\n\nPlease finish the report below so the "
		"KRCS team can respond.",
		"notReport": "I could not find signs of illness in your message.\n\nIs a person or an animal sick?",
		"notReportSick": "Someone is sick",
		"notReportOther": "Something else",
		"notReportPassed": "Thank you. Your message has been passed to the KRCS team, who will follow up if needed.\n\n"
		f"For an emergency call *999* or *112*. KRCS toll-free: *{HOTLINE}*.",
		"reviewFilled": "Some answers were taken from your message. Please check them before you submit.",
		"review": lambda summary: f"*Review your surveillance report*\n\n{summary}\n\nReady to submit this report to the KRCS surveillance desk?",
		"submit": "Confirm & submit",
		"edit": "Back / edit",
		"cancel": "Discard report",
		"editPrompt": "*Which section would you like to edit?*",
		"editBack": "Back to review",
		"incomplete": lambda what: f"Please complete: *{what}*",
		"duplicate": lambda r: f"*Potential duplicate report detected*\n\n*{r['name']}* – {r.get('symptom_tags') or 'same symptoms'}, "
		f"reported on {r.get('report_date')}, is still open in this region.\n\nIs this a separate incident?",
		"submitAnyway": "New incident",
		"consentAsk": "*Attachments*\n\nDoes any photo, video, voice note or file show or record a person? If yes, did they (or a parent or guardian, for a child) agree?",
		"consentNone": "No person in them",
		"consentPerson": "Person agreed",
		"consentGuardian": "Parent agreed",
		"consentRemove": "Remove them",
		"consentRemoved": "The attachments were removed. Your report will be sent without them.",
		"saveFailed": "Your report could not be saved. Please tap *Confirm & submit* to try again.",
		"areaMissing": "*Your area is not set*\n\nYour account has no assigned region and sub-county, so reports cannot be "
		"sent from it yet. Please ask your supervisor to set them, then try again.\n\n"
		f"To report something urgent now, call *{HOTLINE}* _(free, 24/7)_.",
		"done": lambda ref: f"*Report received*\n\nReference: *{ref}*\n\nThe KRCS surveillance team has been notified and a response team will follow up. "
		f"Keep this reference to check the status of your report.\n\nHotline: *{HOTLINE}* _(free, 24/7)_",
		"advice": "Health advice",
		"another": "Report another",
		"finish": "Done",
		"next": "What would you like to do next?",
		"f": {
			"reporter_name": "Name",
			"category": "Category",
			"signal_type": "Signal type",
			"symptoms": "Symptoms",
			"affected_count": "Number affected",
			"age_group": "Age group",
			"animal_exposure": "Animal contact",
			"deaths_count": "Deaths",
			"onset_date": "Onset",
			"region": "Region",
			"sub_county": "Sub-county",
			"place": "Exact location",
			"extra": "Supporting info",
			"description": "Your message",
		},
		"card": {
			"what": "Condition",
			"where": "Location",
			"affected": "Affected",
			"reported": "Reported",
			"status": "Status",
		},
		"attached": lambda files, notes: f"{files} file(s), {notes} note(s)",
	},
	"sw": {
		"help": HELP_SW,
		"invalid": "Samahani, sijaelewa. Tafadhali chagua mojawapo ya chaguo, au andika *menyu*.",
		"emergency": f"Ikiwa maisha ya mtu yako hatarini, piga *999* au *112* sasa. Nambari ya bure ya KRCS: *{HOTLINE}* _(bure, saa 24)_.",
		"errorGeneric": f"Samahani, kuna hitilafu upande wetu. Andika *menyu* kuanza upya, au piga *{HOTLINE}*.",
		"welcome": "*Karibu Kenya Red Cross Society*\n\nMimi ni Msaidizi wa Ufuatiliaji wa Afya na Tahadhari za Jamii wa KRCS.\n\n"
		"_Nikihudumia wahudumu wa afya walioidhinishwa na wanajamii kote Kenya._\n\nTafadhali chagua:",
		"roleCommunity": "Mwanajamii",
		"roleStaff": "Mfanyakazi wa KRCS",
		"roleHelp": "Msaada na dharura",
		"notStaff": lambda phone: f"Nambari hii ya WhatsApp (*{phone}*) haijaunganishwa na akaunti hai ya mfanyakazi wa KRCS.\n\n"
		"Mwombe msimamizi wako aiongeze kama *Mobile No* kwenye wasifu wako wa KRCS, au endelea kama mwanajamii.",
		"back": "Rudi",
		"staffVerified": _staff_sw,
		"portal": "*Mfumo wa Ufuatiliaji wa Afya wa KRCS*\n\nChagua hapa chini kuendelea:",
		"menuReport": "Tuma taarifa ya afya",
		"menuStatus": "Hali ya taarifa",
		"menuRecent": "Taarifa zangu",
		"menuHelp": "Msaada",
		"submitReport": "Tuma taarifa",
		"backToMenu": "Menyu kuu",
		"menuAsk": "Uliza swali",
		"askPrompt": "*Uliza swali*\nAndika swali lako, k.m. _Nifanye nini nikishuku kipindupindu?_\n\n"
		"Majibu yanatoka tu kwenye miongozo iliyoidhinishwa na KRCS. Andika *menyu* kurudi.",
		"askPromptCommunity": "*Uliza swali*\nAndika swali lako. Kama hakuna jibu lililoidhinishwa, litatumwa kwa timu ya KRCS.\n\n"
		"Kwa dharura piga *999* au *112*. Andika *menyu* kurudi.",
		"askClarify": "Ulimaanisha lipi kati ya haya? Chagua moja, au andika swali lako tena.",
		"askRouted": "Hii inaonekana kuwa taarifa ya watu walio wagonjwa. Tafadhali itume kama taarifa ili timu ya ufuatiliaji iipokee.",
		"askMixed": "Kama kuna watu wagonjwa sasa, tafadhali tuma pia taarifa.",
		"askCount": "Idadi ya ripoti haipatikani kwenye WhatsApp. Tafadhali tumia ukurasa wa *Ripoti* kwenye programu ya ufuatiliaji ya KRCS.",
		"askTeam": "timu ya ufuatiliaji ya KRCS",
		"askUnavailable": lambda contact: f"Huduma ya miongozo haipatikani kwa sasa, kwa hivyo sijajibu. Swali lako limetumwa kwa {contact}. "
		"Ikiwa ni dharura, fuata utaratibu wako wa kawaida wa kuripoti dharura.",
		"statusTitle": "*Hali ya taarifa zako*",
		"recentTitle": "*Taarifa zako za karibuni*",
		"mineEmpty": "Bado hujatuma taarifa yoyote.",
		"mineHint": "_Tuma namba ya kumbukumbu (k.m. RPT-012) kuona taarifa moja._",
		"submitNew": "Tuma taarifa mpya",
		"refNotFound": lambda ref: f"Hakuna taarifa *{ref}* kati ya taarifa zako.",
		"resume": "*Una taarifa ambayo hukumaliza.*\nUngependa kuendelea ulipoishia?",
		"paused": lambda minutes: f"*Mazungumzo yamesitishwa*\n\nMazungumzo yako yamesitishwa baada ya dakika {minutes} bila shughuli. "
		"Taarifa yako ambayo hukumaliza imehifadhiwa kama rasimu.\n\nUngependa kuendelea ulipoishia?",
		"resumeBtn": "Endelea",
		"restartBtn": "Anza upya",
		"cancelled": "*Taarifa imefutwa*\n\nRasimu ya taarifa yako imeghairiwa. Hakuna kilichotumwa.",
		"media": {"image": "Picha", "document": "Hati", "audio": "Ujumbe wa sauti", "video": "Video"},
		"mediaAdded": lambda what, n: f"*{what} imeambatanishwa*\n\nVitu vilivyoambatanishwa: *{n}*",
		"mediaRefused": "Aina hii ya faili haiwezi kuongezwa kwenye taarifa. Tafadhali tuma picha, video, ujumbe wa sauti au PDF.",
		"mediaNotSaved": lambda ref, n: f"Taarifa *{ref}* imehifadhiwa, lakini faili {n} hazikuweza kuongezwa. Kila faili lisizidi MB 10.",
		"moreOrReview": "_Unaweza kuongeza picha, hati au ujumbe wa sauti zaidi, au bonyeza *Endelea kukagua*._",
		"skip": "Ruka",
		"more": "Zaidi",
		"prev": "Nyuma",
		"listButton": "Chagua",
		"name": lambda n, t, profile: f"{_step_sw(n, t, 'Jina lako')}\nJina lako ni nani?"
		+ ("\n\nBonyeza kitufe kama ni sahihi, au andika jina lako." if profile else "\n\nAndika jina lako."),
		"nameInvalid": "Tafadhali andika jina lako (angalau herufi 2).",
		"category": lambda n, t: f"{_step_sw(n, t, 'Aina ya tukio')}\nChagua aina ya tukio la afya ya jamii:",
		"signal": lambda n, t: f"{_step_sw(n, t, 'Aina ya ishara')}\nUnaripoti tukio gani la afya?",
		"symptomCommon": lambda n,
		t,
		chosen: f"{_step_sw(n, t, 'Unaripoti nini?')}\n{_chosen('Zilizochaguliwa', chosen)}"
		"Chagua dalili unayoona. Unaweza kuchagua zaidi ya moja.\n\n"
		"Haipo kwenye orodha? Chagua *Dalili nyingine*, au eleza unachoona kwa maneno yako, k.m. _homa na kuhara_.",
		"symptomOther": "Dalili nyingine",
		"symptomOtherDesc": "Dalili zote, kwa aina ya tatizo",
		"symptomCommonBack": "Dalili za kawaida",
		"symptomGroup": lambda n,
		t,
		chosen: f"{_step_sw(n, t, 'Unaripoti nini?')}\n{_chosen('Zilizochaguliwa', chosen)}"
		"Ni tatizo la aina gani? Kila chaguo linaonyesha mifano.",
		"symptom": lambda group: f"*{group}*\nChagua dalili unayoona, au andika jina lake.",
		"symptomAll": lambda n,
		t,
		chosen: f"{_step_sw(n, t, 'Unaripoti nini?')}\n{_chosen('Zilizochaguliwa', chosen)}"
		"Chagua dalili unayoona, au andika jina lake. Unaweza kuchagua zaidi ya moja.",
		"symptomBack": "Makundi mengine",
		"symptomNotFound": "Sijaelewa dalili hiyo. Chagua kwenye orodha, au ieleze kwa maneno rahisi, k.m. _homa_, _kikohozi_, _kuhara_.",
		"symptomsMore": lambda items: f"*Dalili zilizochaguliwa:*\n{items}\n\nOngeza dalili nyingine, au endelea?",
		"symptomsAdd": "Ongeza nyingine",
		"symptomsDone": "Endelea",
		"symptomsClear": "Futa",
		"count": lambda n, t, who: f"{_step_sw(n, t, 'Idadi walioathirika')}\nNi "
		+ ("wanyama" if who == "animals" else "watu au wanyama" if who == "both" else "watu")
		+ " wangapi wana dalili hizi? Bonyeza *Mmoja tu*, au andika idadi, k.m. 10.",
		"countOne": "Mmoja tu",
		"countInvalid": "*Idadi si sahihi*\n\nTafadhali andika namba kamili kati ya 1 na 100000.\n\nMfano: `10`",
		"age": lambda n, t: f"{_step_sw(n, t, 'Umri')} _(si lazima)_\nWagonjwa wana umri gani?",
		"exposure": lambda n, t: f"{_step_sw(n, t, 'Kugusana na wanyama')} _(si lazima)_\n"
		"Je, mgonjwa aliumwa au kukwaruzwa na mnyama, au alishika mnyama mgonjwa au aliyekufa?",
		"deaths": lambda n,
		t: f"{_step_sw(n, t, 'Vifo')}\nKuna aliyekufa? Andika idadi ya vifo, au bonyeza *Hakuna*.",
		"deathsNone": "Hakuna",
		"deathsInvalid": "Tafadhali andika idadi ya vifo (0 au zaidi), au bonyeza *Hakuna*.",
		"region": lambda n, t: f"{_step_sw(n, t, 'Linatokea wapi?')}\nChagua eneo:",
		"regionYours": "Eneo lako",
		"subCounty": lambda n,
		t,
		region: f"{_step_sw(n, t, 'Kaunti ndogo')}\nKaunti ndogo ipi ya *{region}*?",
		"place": lambda n,
		t: f"{_step_sw(n, t, 'Mahali hasa')} _(si lazima)_\nTuma mahali ulipo, andika kijiji, block ya kambi au alama inayojulikana, au ruka.",
		"placeGps": "Tuma mahali nilipo",
		"placeGpsPrompt": "Bonyeza *Send location* kutuma mahali hili linapotokea.\n\n_Au andika jina la mahali, au *ruka*._",
		"placeRequired": lambda n,
		t: f"{_step_sw(n, t, 'Mahali hasa')}\nBonyeza *Send location* kutuma mahali tukio linapotokea. "
		"Unaweza kutuma mahali ulipo sasa, au kutafuta au kuchagua mahali kwenye ramani.",
		"placePinPrompt": "Bonyeza *Send location* kutuma mahali kwenye ramani.",
		"placeNeedPin": lambda name: f"Nimeandika: *{name}*.\nMahali kwenye ramani pia panahitajika.",
		"placeName": "Tafadhali andika jina la mahali: kijiji, block ya kambi au alama inayojulikana.",
		"placeNoSkip": "Mahali panahitajika kwa taarifa hii. Bonyeza *Send location* hapo juu, au andika jina la mahali.",
		"placeReceived": lambda coords, name, area=None: f"*Mahali pamepokelewa*\n\nKuratibu: `{coords}`"
		+ (f"\nEneo: *{name}*" if name else "")
		+ (f"\nKaunti ndogo na eneo: *{area}* (unaweza kubadilisha wakati wa kukagua)" if area else ""),
		"onset": lambda n, t: f"{_step_sw(n, t, 'Ilianza lini?')}\nDalili za kwanza zilionekana lini?",
		"onsetToday": "Leo",
		"onsetYesterday": "Jana",
		"onsetOther": "Tarehe maalum",
		"onsetDate": "Andika tarehe dalili za kwanza zilipoonekana, kama *DD/MM/YYYY* (k.m. 28/09/2026).",
		"onsetInvalid": "Tarehe hiyo si sahihi. Tumia *DD/MM/YYYY*, isiwe ya baadaye na iwe ndani ya miezi 12 iliyopita.",
		"extra": lambda n, t, count: f"{_step_sw(n, t, 'Maelezo ya ziada')} _(si lazima)_\n"
		"Ambatanisha picha, majibu ya maabara, hati au ujumbe wa sauti, au andika maelezo zaidi. Unaweza kutuma kadhaa."
		+ (
			f"\n\n_Vitu {count} vimeambatanishwa._\n\nUkimaliza, bonyeza *Endelea kukagua*."
			if count
			else "\n\nHuna cha kuongeza? Bonyeza *Ruka na kagua*."
		),
		"extraReview": "Endelea kukagua",
		"extraSkip": "Ruka na kagua",
		"stepFooter": "Andika rudi kurudi nyuma, ghairi kusimamisha",
		"noteAdded": lambda note, n: f'*Maelezo yameongezwa:*\n_"{note}"_\n\nVitu vilivyoambatanishwa: *{n}*',
		"describe": "*Tueleze kinachotokea*\nKwa maneno yako: nani ni mgonjwa, dalili gani unaona, watu au wanyama wangapi, wapi, "
		"na tangu lini.\n\n_Mfano: Watoto 5 katika Ifo camp, Dadaab wanaharisha na kutapika tangu jana._\n\n"
		"Andika kwa Kiswahili au Kiingereza. Ungependa kujibu swali moja moja? Bonyeza *Hatua kwa hatua*.",
		"describeGuided": "Hatua kwa hatua",
		"describeMedia": "Picha imehifadhiwa na taarifa yako. Tafadhali pia andika maelezo mafupi ya kinachotokea, au bonyeza "
		"*Hatua kwa hatua*.",
		"describeVoice": "Ujumbe wa sauti umehifadhiwa na taarifa yako. Haukuweza kusomwa kiotomatiki, kwa hivyo "
		"tafadhali pia andika maelezo mafupi, au bonyeza *Hatua kwa hatua*.",
		"heard": lambda words: f'*Kutoka kwenye ujumbe wako wa sauti:*\n_"{words}"_\n\nTafadhali kagua majibu hapa chini, kwani maneno huenda yasiwe sahihi kabisa.',
		"clinicalBoundary": "Siwezi kuthibitisha ugonjwa wa mtu, wala kushauri kuhusu dawa au vipimo vyake. Mhudumu wa afya anahitaji "
		"kumchunguza mtu huyo, kwa hivyo tafadhali mpeleke kituo cha afya kilicho karibu.",
		"privacyFull": "*Faragha yako*\n\n*Nani:* Shirika la Msalaba Mwekundu la Kenya linawajibika kwa taarifa zako. "
		f"Simu {CONTACT['phone']}, {CONTACT['emails'][0]}, {CONTACT['office']}.\n\n"
		"*Kwa nini:* kugundua na kukabili milipuko ya magonjwa.\n\n"
		"*Nani anaziona:* wafanyakazi wa afya wa KRCS walioidhinishwa, ambao wanaweza kushiriki kinachohitajika na Wizara ya Afya. "
		"WhatsApp (Meta) hubeba ujumbe huu na kuuchakata nje ya Kenya. Mifumo ya KRCS, iliyoko Kenya, husoma maneno yako ili "
		"kujaza taarifa yako na kujibu maswali yako.\n\n"
		"*Haki zako:* unaweza kuomba kuona, kusahihisha au kufuta taarifa zako, kupinga matumizi yake, au kuondoa idhini yako "
		f"wakati wowote, hapa au kwa kupiga *{HOTLINE}*. Mhudumu wa Afya ya Jamii anaweza kukusaidia.\n\n"
		"*Malalamiko:* wasiliana na KRCS, au Ofisi ya Kamishna wa Ulinzi wa Data.\n\n"
		"Tafadhali usitume picha au sauti za watu bila ruhusa yao.",
		"privacyAsk": "Ungependa kufanya nini?",
		"privacyWithdraw": "Ondoa idhini",
		"privacyRequest": "Ona au futa data",
		"privacyWithdrawn": "Idhini yako imeondolewa na taarifa yoyote ambayo haijakamilika imefutwa. Hatutapokea taarifa kutoka nambari "
		f"hii isipokuwa ukikubali tena. Kufuta taarifa ulizokwisha tuma, andika *FARAGHA* au piga *{HOTLINE}*.",
		"privacyRequested": "Ombi lako limetumwa kwa timu ya KRCS, ambayo itawasiliana nawe kupitia nambari hii.",
		"describeLocation": "Mahali pamehifadhiwa. Sasa andika maelezo mafupi ya kinachotokea, au bonyeza *Hatua kwa hatua*.",
		"noted": _noted_sw,
		"urgent": "*Hali hii inaweza kuwa hatari.* Kama kuna mtu aliye mgonjwa sana, aliyepoteza fahamu, anayetokwa na damu au "
		"anayepumua kwa shida, mpeleke kituo cha afya kilicho karibu sasa hivi au piga *999* / *112*. Nambari ya bure ya KRCS: "
		f"*{HOTLINE}*.\n\nTafadhali kamilisha taarifa hapa chini ili timu ya KRCS ichukue hatua.",
		"notReport": "Sijaona dalili za ugonjwa kwenye ujumbe wako.\n\nJe, kuna mtu au mnyama aliye mgonjwa?",
		"notReportSick": "Kuna mgonjwa",
		"notReportOther": "Jambo lingine",
		"notReportPassed": "Asante. Ujumbe wako umetumwa kwa timu ya KRCS, ambayo itafuatilia ikihitajika.\n\n"
		f"Kwa dharura piga *999* au *112*. Nambari ya bure ya KRCS: *{HOTLINE}*.",
		"reviewFilled": "Baadhi ya majibu yamechukuliwa kutoka kwa ujumbe wako. Tafadhali yakague kabla ya kutuma.",
		"review": lambda summary: f"*Kagua taarifa yako ya ufuatiliaji*\n\n{summary}\n\nUko tayari kutuma taarifa hii kwa dawati la ufuatiliaji la KRCS?",
		"submit": "Thibitisha na tuma",
		"edit": "Rudi / badilisha",
		"cancel": "Futa taarifa",
		"editPrompt": "*Ungependa kubadilisha sehemu gani?*",
		"editBack": "Rudi kukagua",
		"incomplete": lambda what: f"Tafadhali kamilisha: *{what}*",
		"duplicate": lambda r: f"*Huenda taarifa hii tayari ipo*\n\n*{r['name']}* – {r.get('symptom_tags') or 'dalili zilezile'}, "
		f"iliyotumwa {r.get('report_date')}, bado iko wazi katika eneo hili.\n\nJe, hili ni tukio tofauti?",
		"submitAnyway": "Tukio jipya",
		"consentAsk": "*Viambatisho*\n\nJe, picha, video, sauti au faili yoyote inaonyesha au inarekodi mtu? Kama ndiyo, je alikubali (au mzazi au mlezi, kwa mtoto)?",
		"consentNone": "Hakuna mtu",
		"consentPerson": "Mtu alikubali",
		"consentGuardian": "Mzazi alikubali",
		"consentRemove": "Ziondoe",
		"consentRemoved": "Viambatisho vimeondolewa. Taarifa yako itatumwa bila hivyo.",
		"saveFailed": "Taarifa yako haikuweza kuhifadhiwa. Tafadhali bonyeza *Thibitisha na tuma* kujaribu tena.",
		"areaMissing": "*Eneo lako halijawekwa*\n\nAkaunti yako haina eneo na kaunti ndogo ulizopangiwa, kwa hiyo bado "
		"huwezi kutuma taarifa. Tafadhali mwombe msimamizi wako aziweke, kisha ujaribu tena.\n\n"
		f"Kuripoti jambo la dharura sasa, piga *{HOTLINE}* _(bure, saa 24)_.",
		"done": lambda ref: f"*Taarifa imepokelewa*\n\nNamba ya kumbukumbu: *{ref}*\n\nTimu ya ufuatiliaji ya KRCS imearifiwa na timu ya kukabiliana itafuatilia. "
		f"Hifadhi namba hii kuangalia hali ya taarifa yako.\n\nNambari ya dharura: *{HOTLINE}* _(bure, saa 24)_",
		"advice": "Ushauri wa afya",
		"another": "Taarifa nyingine",
		"finish": "Maliza",
		"next": "Ungependa kufanya nini sasa?",
		"f": {
			"reporter_name": "Jina",
			"category": "Aina",
			"signal_type": "Aina ya ishara",
			"symptoms": "Dalili",
			"affected_count": "Idadi",
			"age_group": "Umri",
			"animal_exposure": "Kugusana na wanyama",
			"deaths_count": "Vifo",
			"onset_date": "Ilianza",
			"region": "Eneo",
			"sub_county": "Kaunti ndogo",
			"place": "Mahali hasa",
			"extra": "Maelezo ya ziada",
			"description": "Ujumbe wako",
		},
		"card": {
			"what": "Tukio",
			"where": "Mahali",
			"affected": "Walioathirika",
			"reported": "Ilitumwa",
			"status": "Hali",
		},
		"attached": lambda files, notes: f"faili {files}, maelezo {notes}",
	},
}
