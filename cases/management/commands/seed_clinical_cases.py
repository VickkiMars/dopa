import uuid
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

from accounts.models import Role
from cases.models import Case, CaseTeam, CaseStatus, DiagnosisRanking, Decision
from collaboration.models import Hypothesis, HypothesisStatus, DiscussionNote
from audit.models import AuditLog, AuditAction, AuditStatus

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds the DOPA platform with the 3 synthetic clinical scenarios from Appendix A."

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            type=str,
            default='ClinicPassword123!',
            help="Default password for seeded clinical accounts (default: ClinicPassword123!)"
        )
        parser.add_argument(
            '--clean',
            action='store_true',
            help="Purge existing seeded data before creating"
        )

    def handle(self, *args, **options):
        password = options['password']
        self.stdout.write(self.style.NOTICE("Seeding synthetic clinical scenarios from Appendix A..."))

        with transaction.atomic():
            # -------------------------------------------------------------
            # 1. Clinicians (Primary Physicians & Specialists)
            # -------------------------------------------------------------
            def get_or_create_user(email, full_name, role):
                clean_email = email.lower().strip()
                try:
                    user = User.objects.get(email=clean_email)
                    user.set_password(password)
                    user.full_name = full_name
                    user.role = role
                    user.is_active = True
                    user.save()
                    return user
                except User.DoesNotExist:
                    return User.objects.create_user(
                        email=clean_email,
                        password=password,
                        full_name=full_name,
                        role=role
                    )

            # Primary Physicians
            dr_bassey = get_or_create_user('dr.bassey@clinic.org', 'Dr. O. Bassey', Role.PRIMARY_PHYSICIAN)
            dr_adeyemi = get_or_create_user('dr.adeyemi@clinic.org', 'Dr. M. Adeyemi', Role.PRIMARY_PHYSICIAN)
            dr_danjuma = get_or_create_user('dr.danjuma@clinic.org', 'Dr. R. Danjuma', Role.PRIMARY_PHYSICIAN)

            # Specialists
            dr_bello = get_or_create_user('dr.bello@clinic.org', 'Dr. A. Bello', Role.SPECIALIST)
            dr_okafor = get_or_create_user('dr.okafor@clinic.org', 'Dr. E. Okafor', Role.SPECIALIST)
            dr_ibrahim = get_or_create_user('dr.ibrahim@clinic.org', 'Dr. K. Ibrahim', Role.SPECIALIST)
            dr_nwosu = get_or_create_user('dr.nwosu@clinic.org', 'Dr. C. Nwosu', Role.SPECIALIST)
            dr_taiwo = get_or_create_user('dr.taiwo@clinic.org', 'Dr. F. Taiwo', Role.SPECIALIST)

            self.stdout.write(self.style.SUCCESS("  [✓] Clinical user accounts configured."))

            # -------------------------------------------------------------
            # Helper to log audit events
            # -------------------------------------------------------------
            def audit(action, actor, case, entity_type='', entity_id='', details=None, status=AuditStatus.ALLOWED):
                AuditLog.objects.create(
                    action=action,
                    actor=actor,
                    case_id=case.id,
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    ip_address='127.0.0.1',
                    status=status,
                    details=details or {}
                )

            # -------------------------------------------------------------
            # 2. Clinical Scenario 1: Multi-System Fever, Joint Pain & Rash
            # -------------------------------------------------------------
            case1, _ = Case.objects.get_or_create(
                title="Multi-system Presentation of Recurrent High Fever, Arthralgia, and Salmon-Colored Rash",
                owner=dr_bassey,
                defaults={
                    'clinical_summary': (
                        "A 28-year-old female presents with daily quotidian fevers spiking up to 39.5°C over 4 weeks, "
                        "symmetrical migratory arthralgia affecting wrists and knees, and an evanescent salmon-pink macular "
                        "rash on the trunk appearing during fever spikes."
                    ),
                    'history': "No prior autoimmune disease; no recent travel; no tick exposure; antibiotics had no effect.",
                    'findings': (
                        "Vitals: Temp 39.4°C, HR 108 bpm, BP 115/75 mmHg.\n"
                        "Labs: Leukocytosis (WBC 18.5 x 10^9/L, 88% neutrophils), Ferritin 4,200 ng/mL (dramatically elevated), "
                        "ESR 85 mm/hr, CRP 120 mg/L, ANA negative, Rheumatoid Factor negative, blood cultures x 3 negative.\n"
                        "Imaging: Hepatosplenomegaly on abdominal ultrasound."
                    ),
                    'status': CaseStatus.CLOSED
                }
            )
            audit(AuditAction.CASE_CREATED, dr_bassey, case1, 'cases_case', case1.id, {'title': case1.title})

            # Admitted Specialists
            for sp in [dr_bello, dr_okafor]:
                CaseTeam.objects.get_or_create(case=case1, specialist=sp, defaults={'admitted_by': dr_bassey})
                audit(AuditAction.SPECIALIST_ADMITTED, dr_bassey, case1, 'cases_caseteam', '', {'specialist_email': sp.email})

            # Hypotheses
            h1_1, _ = Hypothesis.objects.get_or_create(
                case=case1,
                specialist=dr_bello,
                proposed_diagnosis="Adult-Onset Still's Disease (AOSD)",
                defaults={
                    'rationale': "Quotidian fevers, evanescent non-pruritic salmon rash coinciding with fever spikes, extreme hyperferritinemia (>4,000 ng/mL), negative ANA/RF strongly fulfill Yamaguchi criteria.",
                    'supporting_evidence': "Ferritin 4,200 ng/mL, WBC 18.5 with neutrophilia, negative blood cultures.",
                    'status': HypothesisStatus.ACTIVE
                }
            )
            audit(AuditAction.HYPOTHESIS_SUBMITTED, dr_bello, case1, 'collaboration_hypothesis', h1_1.id, {'proposed_diagnosis': h1_1.proposed_diagnosis})

            h1_2, _ = Hypothesis.objects.get_or_create(
                case=case1,
                specialist=dr_okafor,
                proposed_diagnosis="Systemic Lupus Erythematosus (SLE)",
                defaults={
                    'rationale': "Young female presenting with systemic fever, arthralgia, and rash; need to exclude atypical ANA-negative SLE variant.",
                    'supporting_evidence': "Symmetrical polyarthralgia and cutaneous involvement.",
                    'status': HypothesisStatus.ACTIVE
                }
            )
            audit(AuditAction.HYPOTHESIS_SUBMITTED, dr_okafor, case1, 'collaboration_hypothesis', h1_2.id, {'proposed_diagnosis': h1_2.proposed_diagnosis})

            # Discussion Notes
            n1_1, _ = DiscussionNote.objects.get_or_create(
                case=case1, author=dr_bello,
                defaults={'body': "Serum ferritin of 4,200 ng/mL is five times higher than typical reactive elevations. Strongly supportive of AOSD."}
            )
            audit(AuditAction.DISCUSSION_POSTED, dr_bello, case1, 'collaboration_discussionnote', n1_1.id, {'snippet': n1_1.body[:50]})

            # Differential Ranking
            DiagnosisRanking.objects.filter(case=case1).delete()
            r1_1 = DiagnosisRanking.objects.create(case=case1, hypothesis=h1_1, rank_position=1)
            r1_2 = DiagnosisRanking.objects.create(case=case1, hypothesis=h1_2, rank_position=2)
            audit(AuditAction.RANK_UPDATED, dr_bassey, case1, 'cases_diagnosisranking', r1_1.id, {'new_rank': 1, 'direction': 'UP'})

            # Final Decision
            Decision.objects.filter(case=case1).delete()
            d1 = Decision.objects.create(
                case=case1,
                decider=dr_bassey,
                final_diagnosis="Adult-Onset Still's Disease (AOSD); initiate high-dose corticosteroids after infectious clearance.",
                advisory_acknowledged=True,
                governance_statement="I acknowledge that specialist hypotheses and differential rankings are advisory only. I retain sole clinical responsibility for the final diagnosis and subsequent management plan."
            )
            audit(AuditAction.DECISION_RECORDED, dr_bassey, case1, 'cases_decision', d1.id, {'final_diagnosis': d1.final_diagnosis, 'advisory_acknowledged': True})

            self.stdout.write(self.style.SUCCESS("  [✓] Scenario 1 seeded (AOSD)."))

            # -------------------------------------------------------------
            # 3. Clinical Scenario 2: Refractory Chronic Microcytic Anaemia
            # -------------------------------------------------------------
            case2, _ = Case.objects.get_or_create(
                title="Refractory Severe Microcytic Hypochromic Anaemia in a Middle-Aged Male",
                owner=dr_adeyemi,
                defaults={
                    'clinical_summary': "A 52-year-old male presents with profound fatigue, exertional dyspnoea, and pallor unresponsive to 6 months of oral iron supplementation.",
                    'history': "Denies overt gastrointestinal bleeding, hematochezia, or melena. No family history of hemoglobinopathy.",
                    'findings': (
                        "Vitals: HR 96 bpm, BP 125/80 mmHg.\n"
                        "Labs: Hb 7.2 g/dL, MCV 64 fL (profound microcytosis), Ferritin 12 ng/mL (low), Serum Iron 20 ug/dL, Total Iron Binding Capacity 450 ug/dL. Stool occult blood positive x 2.\n"
                        "Diagnostics: Upper endoscopy unremarkable; initial colonoscopy revealed minor non-bleeding diverticula."
                    ),
                    'status': CaseStatus.CLOSED
                }
            )
            audit(AuditAction.CASE_CREATED, dr_adeyemi, case2, 'cases_case', case2.id, {'title': case2.title})

            # Admitted Specialists
            for sp in [dr_ibrahim, dr_nwosu]:
                CaseTeam.objects.get_or_create(case=case2, specialist=sp, defaults={'admitted_by': dr_adeyemi})
                audit(AuditAction.SPECIALIST_ADMITTED, dr_adeyemi, case2, 'cases_caseteam', '', {'specialist_email': sp.email})

            # Hypotheses
            h2_1, _ = Hypothesis.objects.get_or_create(
                case=case2,
                specialist=dr_ibrahim,
                proposed_diagnosis="Occult Small-Bowel Angiodysplasia / Vascular Ectasia",
                defaults={
                    'rationale': "Persistent iron-deficiency anaemia with positive occult blood and negative bidirectional endoscopy suggests mid-gut bleeding inaccessible to standard endoscopes.",
                    'supporting_evidence': "Refractory iron deficiency, positive fecal occult blood, normal colonoscopy.",
                    'status': HypothesisStatus.ACTIVE
                }
            )
            audit(AuditAction.HYPOTHESIS_SUBMITTED, dr_ibrahim, case2, 'collaboration_hypothesis', h2_1.id, {'proposed_diagnosis': h2_1.proposed_diagnosis})

            h2_2, _ = Hypothesis.objects.get_or_create(
                case=case2,
                specialist=dr_nwosu,
                proposed_diagnosis="Celiac Disease with Duodenal Malabsorption",
                defaults={
                    'rationale': "Severe failure of oral iron absorption can indicate blunted enterocyte transport from gluten enteropathy even without classic diarrhea.",
                    'supporting_evidence': "Complete failure of oral iron response over 6-month trial.",
                    'status': HypothesisStatus.ACTIVE
                }
            )
            audit(AuditAction.HYPOTHESIS_SUBMITTED, dr_nwosu, case2, 'collaboration_hypothesis', h2_2.id, {'proposed_diagnosis': h2_2.proposed_diagnosis})

            # Differential Ranking
            DiagnosisRanking.objects.filter(case=case2).delete()
            r2_1 = DiagnosisRanking.objects.create(case=case2, hypothesis=h2_1, rank_position=1)
            r2_2 = DiagnosisRanking.objects.create(case=case2, hypothesis=h2_2, rank_position=2)
            audit(AuditAction.RANK_UPDATED, dr_adeyemi, case2, 'cases_diagnosisranking', r2_1.id, {'new_rank': 1, 'direction': 'UP'})

            # Final Decision
            Decision.objects.filter(case=case2).delete()
            d2 = Decision.objects.create(
                case=case2,
                decider=dr_adeyemi,
                final_diagnosis="Occult gastrointestinal bleeding secondary to suspected small bowel angiodysplasia; proceed with video capsule endoscopy.",
                advisory_acknowledged=True,
                governance_statement="I acknowledge that specialist hypotheses and differential rankings are advisory only. I retain sole clinical responsibility for the final diagnosis and subsequent management plan."
            )
            audit(AuditAction.DECISION_RECORDED, dr_adeyemi, case2, 'cases_decision', d2.id, {'final_diagnosis': d2.final_diagnosis, 'advisory_acknowledged': True})

            self.stdout.write(self.style.SUCCESS("  [✓] Scenario 2 seeded (Occult Angiodysplasia)."))

            # -------------------------------------------------------------
            # 4. Clinical Scenario 3: Pediatric Episodic Unresponsiveness
            # -------------------------------------------------------------
            case3, _ = Case.objects.get_or_create(
                title="Episodic Staring and Unresponsiveness in an 8-Year-Old Child",
                owner=dr_danjuma,
                defaults={
                    'clinical_summary': "An 8-year-old boy presents with daily brief episodes (5–15 seconds) of vacant staring and speech interruption noted by classroom teachers, occurring 10 to 20 times daily.",
                    'history': "Normal developmental milestones; no aura; immediate recovery without post-ictal confusion.",
                    'findings': (
                        "Vitals: Normal pediatric ranges.\n"
                        "Neurological Exam: Cranial nerves intact, normal tone and reflexes. Hyperventilation during clinical exam reliably precipitates a 10-second staring spell.\n"
                        "Diagnostics: Resting routine 20-minute EEG captured during clinic visit."
                    ),
                    'status': CaseStatus.CLOSED
                }
            )
            audit(AuditAction.CASE_CREATED, dr_danjuma, case3, 'cases_case', case3.id, {'title': case3.title})

            # Admitted Specialist
            CaseTeam.objects.get_or_create(case=case3, specialist=dr_taiwo, defaults={'admitted_by': dr_danjuma})
            audit(AuditAction.SPECIALIST_ADMITTED, dr_danjuma, case3, 'cases_caseteam', '', {'specialist_email': dr_taiwo.email})

            # Hypotheses
            h3_1, _ = Hypothesis.objects.get_or_create(
                case=case3,
                specialist=dr_taiwo,
                proposed_diagnosis="Childhood Absence Epilepsy (CAE)",
                defaults={
                    'rationale': "Classic age of onset, multiple daily brief staring spells without post-ictal state, and immediate precipitation by hyperventilation is pathognomonic for CAE.",
                    'supporting_evidence': "Hyperventilation trigger in clinic; sudden onset and offset of episodes.",
                    'status': HypothesisStatus.ACTIVE
                }
            )
            audit(AuditAction.HYPOTHESIS_SUBMITTED, dr_taiwo, case3, 'collaboration_hypothesis', h3_1.id, {'proposed_diagnosis': h3_1.proposed_diagnosis})

            h3_2, _ = Hypothesis.objects.get_or_create(
                case=case3,
                specialist=dr_taiwo,
                proposed_diagnosis="Behavioral Inattention / Absence Mimic (Stereotypies)",
                defaults={
                    'rationale': "Differential must consider non-epileptic daydreaming or attention-deficit phenomena, though responsiveness to tactile stimuli typically differentiates this.",
                    'supporting_evidence': "Normal baseline neurological development.",
                    'status': HypothesisStatus.ACTIVE
                }
            )
            audit(AuditAction.HYPOTHESIS_SUBMITTED, dr_taiwo, case3, 'collaboration_hypothesis', h3_2.id, {'proposed_diagnosis': h3_2.proposed_diagnosis})

            # Differential Ranking
            DiagnosisRanking.objects.filter(case=case3).delete()
            r3_1 = DiagnosisRanking.objects.create(case=case3, hypothesis=h3_1, rank_position=1)
            r3_2 = DiagnosisRanking.objects.create(case=case3, hypothesis=h3_2, rank_position=2)
            audit(AuditAction.RANK_UPDATED, dr_danjuma, case3, 'cases_diagnosisranking', r3_1.id, {'new_rank': 1, 'direction': 'UP'})

            # Final Decision
            Decision.objects.filter(case=case3).delete()
            d3 = Decision.objects.create(
                case=case3,
                decider=dr_danjuma,
                final_diagnosis="Childhood Absence Epilepsy confirmed; initiate first-line ethosuximide therapy with outpatient EEG confirmation.",
                advisory_acknowledged=True,
                governance_statement="I acknowledge that specialist hypotheses and differential rankings are advisory only. I retain sole clinical responsibility for the final diagnosis and subsequent management plan."
            )
            audit(AuditAction.DECISION_RECORDED, dr_danjuma, case3, 'cases_decision', d3.id, {'final_diagnosis': d3.final_diagnosis, 'advisory_acknowledged': True})

            self.stdout.write(self.style.SUCCESS("  [✓] Scenario 3 seeded (Childhood Absence Epilepsy)."))

        self.stdout.write(self.style.SUCCESS("\nAll 3 Appendix A clinical scenarios successfully seeded into database!"))
