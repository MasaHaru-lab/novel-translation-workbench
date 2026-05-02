# Unresolved Decisions

## Open items

### 嬷嬷 system
- Direction: render as natural English role-equivalent titles where appropriate (e.g., "Nanny Ding" or "Senior Maid Ding") rather than opaque bare pinyin ("Ding Momo")
- Why unresolved: needs system-level decision across household female attendant titles — what English role to use depends on the character's specific function (wet-nurse, senior household maid, children's caretaker) and the register of the scene
- Risk if left unstable: drift between pinyin (`Momo`), natural English titles (`Nanny`, `Nurse`, `Senior Maid`, `Attendant`), and inconsistent renderings

### Official title system
- Current working choice: use readable functional English, but keep titles provisional until a broader official-rank system is established
- Terms already affected: `光禄寺卿`, `贵妃`
- Risk if left unstable: the court and bureaucracy will feel inconsistent from chapter to chapter

### Household-status terms
- Current working choice: `Young Lady` for `大小姐`
- Why unresolved: may require local variation when rank order or branch structure matters
- Risk if handled loosely: loss of household hierarchy, or false mapping to British aristocratic titles

### Clan / branch terminology
- Current working choice: `main branch` for `长房`
- Why unresolved: branch-family terminology may need fuller system treatment later
- Risk if left unstable: kinship and clan structure become muddy in English

### Daoist title handling
- Current working choice: `Chi Yuan Daoist` (赤=chi, 元=yuan, 老道=Daoist; renders 赤 in pinyin for name-like flow)
- Why unresolved: may need refinement depending on the naming system used for religious titles and sobriquets
- Risk if left unstable: tone and naming consistency may drift

### 大夫 / physician address system
- Current working choice: `Doctor [Surname]` (e.g. Doctor Zhang), never `Dr.` and never `Zhang Dafu`
- Why unresolved: emerged from ch1131_v1 real-sample output where the same character was rendered as Dr. Zhang, Doctor Zhang, and Zhang Dafu within a single chapter. The functional title ("Doctor Zhang") matches the existing project pattern for household roles. However, this conflicts with the story's own historical setting where 大夫 is a generational title, not a modern "Doctor." Needs cross-chapter validation before confirming.
- Terms affected: `张大夫`, `高大夫`, `杨大夫`
- Risk if left unstable: every physician character (and this book has many) will suffer the same three-way rendering drift

### 清平观 canonical rendering
- Current working choice: `Qingping Temple` (not Abbey, Monastery, or Shrine)
- Why unresolved: ch1131_v1 output switched between "Qingping Temple" and "Qingping Abbey" within a single chapter. The location appears in many chapters. "Temple" is the more neutral fit within the book's semi-historical setting, but needs confirmation against other chapters where the term appears.
- Risk if left unstable: readers will think Qingping Temple and Qingping Abbey are different places

## Resolved items

### 嫡母
- Resolution: rendered as `legal mother`
- Rationale: preserves the legal-wife distinction from concubine-born structure without sounding legalistic
- Rejected alternatives: `principal mother` (too legalistic/unnatural), plain `mother` (loses hierarchy)
- Date resolved: 2026-04-30

### 丫头 / 西丫头 / 你这丫头 (address-term system)
- Resolution: rendered as `Xi’er`
- Rationale: preserves the elder-to-younger familiar register while reading naturally in English dialogue; the character's given name serves as a consistent address form
- Rejected alternatives: `girl` (too flat, fails register), `little girl` (infantilizing), `Little Xi` (over-Westernized)
- Date resolved: 2026-04-30