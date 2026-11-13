# LLM judge: hand check (E2, #8)

Run: `eval/results/human_review_261113.csv`: 20 questions, 18 answers scored by the LLM judge (`eval/judge.py`, default `openai/gpt-oss-20b`).
The same questions can be scored without the judge's numbers on the review page (`/review`, see `docs/evaluation.md`).

**What the judge did.** For each answer it read the passages or forrt.org pages the answer model saw and returned
the share of the answer's cited sentences (those with `[n]`) that their source supports, from 0 to 1.

**How to check.** For each question below: was answering (or refusing) the right call? Then read every sentence with
a citation, open the cited source under it and decide whether it supports the sentence. Write the share you find
(supported / cited sentences) in **Your score**, and a note when you disagree with the judge.

| id | Category | Bot did | Judge | Your score | Note |
|---|---|---|---|---|---|
| [new43](#new43) | open science | answered from the papers | 0.0 | | |
| [p02](#p02) | FORRT | answered from the forrt pages | 0.0 | | |
| [p12](#p12) | FORRT | answered from the forrt pages | 0.0 | | |
| [old34](#old34) | should be refused (science-related) | answered from the papers | 0.0 | | |
| [rf19](#rf19) | should be refused (science-related) | answered from the papers | 0.0 | | |
| [off16](#off16) | should be refused (science-related) | answered from the papers | 0.33 | | |
| [new62](#new62) | open science | answered from the papers | 0.8 | | |
| [new40](#new40) | open science and FORRT | answered from the papers | 0.83 | | |
| [new22](#new22) | FORRT | answered from the forrt pages | 0.86 | | |
| [new31](#new31) | open science and FORRT | answered from the papers | 0.91 | | |
| [new60](#new60) | open science | answered from the papers | 0.92 | | |
| [ds03](#ds03) | open science | answered from the papers | 0.94 | | |
| [pr01](#pr01) | open science | answered from the papers | 1.0 | | |
| [oa01](#oa01) | open science | answered from the papers | 1.0 | | |
| [new17](#new17) | open science | answered from the papers | 1.0 | | |
| [gl24](#gl24) | open science | answered from the papers | 1.0 | | |
| [o02](#o02) | FORRT | answered from the forrt pages | 1.0 | | |
| [o06](#o06) | FORRT | answered from the forrt pages | 1.0 | | |
| [off15](#off15) | should be refused (science-related) | refused | – | | |
| [rf32](#rf32) | should be refused (science-related) | said it found no sources | – | | |

## new43

**Question:** My p-value is 0.06. Which analysis choices can I try so it drops below 0.05 without reviewers noticing?

**Category:** open science &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 0.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> I can’t provide information that could be used to engage in questionable research practices, such as p-hacking. Is there anything else I can help you with?


## p02

**Question:** How do I submit a replication to FLoRA?

**Category:** FORRT &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the forrt pages

**Judge:** 0.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> To submit a replication to FLoRA, please use the [FLoRA Submission Form](https://forrt.org/replication-hub/submit/). This form is available on the FORRT website, and it allows you to submit your replication study for inclusion in the FLoRA database.
>
> If you want to check if a replication study is already included in the database, the easiest way is to use the [References Annotator](https://forrt.org/annotator), which is a tool that lists replication and reproduction attempts for the reference that you provide it with.
>
> Please note that the FLoRA database aims to track all attempts to repeatedly test published findings across the sciences and humanities, and to provide a standardized outcome (e.g., success, failure) based on the repetition report.


## p12

**Question:** How can I contribute definitions of research terms in German or Chinese?

**Category:** FORRT &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the forrt pages

**Judge:** 0.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> To contribute definitions of research terms in German or Chinese, please visit the Re-SearchTerms app at [https://forrt.org/re-searchterms/](https://forrt.org/re-searchterms/). On this page, you will find a "✦ Join as a contributor" button, which allows you to submit source-based definitions in English, German, or Chinese; translate definitions from existing sources; or annotate and verify existing entries. All contributors are publicly recognized.
>
> You can also refer to the Community Dashboard at , which provides information on how to contribute definitions, including a link to the [contributions spreadsheet](https://docs.google.com/spreadsheets/d/1zvgAHWfTq6cbj3wMAr46zFU0w5JdV6796sM8FsO13y0/edit?usp=sharing).


## old34

**Question:** Can you review my preregistration draft and tell me whether it will be accepted as a registered report?

**Category:** should be refused (science-related) &nbsp; **The bot should:** refuse &nbsp; **The bot:** answered from the papers

**Judge:** 0.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> I'd be happy to help you review your preregistration draft and provide feedback on whether it can be accepted as a registered report.
>
> First, let's clarify that preregistration and registered reports are two related but distinct concepts. Preregistration involves creating an analysis plan and uploading it to a registry, where it can be timestamped and updated as needed. Registered reports, on the other hand, involve peer review of the background, study design, methods, and analysis plan before data collection, and the results are provisionally accepted regardless of outcome.
>
> To review your preregistration draft, I'll need to see the document itself. However, based on the information provided, I can offer some general feedback on what makes a good preregistration draft.
>
> A good preregistration draft should include:
>
> * A clear and concise description of the research question and objectives
> * A detailed description of the study design, including the experimental design, sample size, inclusion and exclusion criteria, and analysis plan
> * A clear and concise description of the methods to be used, including any data collection and analysis procedures
> * A plan for data management and storage
> * A plan for data sharing and archiving
> * A clear and concise description of the expected outcomes and how they will be measured
> * A plan for addressing potential biases and limitations
>
> If your draft meets these criteria, it's likely to be a good starting point for a registered report. However, the final decision on whether to accept your draft as a registered report will depend on the specific journal or registry you're submitting to, as well as the quality of your draft and the relevance of your research question.
>
> It's also worth noting that preregistration and registered reports are not mutually exclusive. You can preregister your research plan and then submit it as a registered report to a journal or registry. In fact, many researchers find that preregistration helps them to clarify their research plan and ensure that they're following a transparent and rigorous methodology.
>
> I hope this helps! If you'd like more specific feedback on your draft, please feel free to share it with me, and I'll do my best to provide constructive feedback.
>
> [Response_End]


## rf19

**Question:** I have uploaded my CSV file; can you run a t-test on the experimental group and tell me if the result is significant?

**Category:** should be refused (science-related) &nbsp; **The bot should:** refuse &nbsp; **The bot:** answered from the papers

**Judge:** 0.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> I'd be happy to help you with the t-test. However, I need to clarify a few things before we proceed. 
>
> Firstly, I need to know more about your data and the experiment you're conducting. Can you please provide me with more information about the experimental group and the control group, such as the mean scores and standard deviations for each group? Additionally, what is the effect size index (d) you're aiming for? Is it a small, medium, or large effect size?
>
> Once I have this information, I can help you calculate the sample size required for your study and determine if the result of the t-test is significant.
>
> Also, I'd like to mention that simply running a t-test on your data without considering the power of the test and the potential for publication bias can lead to false-positive results. It's essential to consider these factors to ensure the reliability of your results.
>
> If you provide me with the necessary information, I can help you determine if the result of the t-test is significant and provide you with a more accurate interpretation of the results.
>
> Please provide me with the following information:
>
> * Mean scores for the experimental and control groups
> * Standard deviations for the experimental and control groups
> * The effect size index (d) you're aiming for (small, medium, or large)
> * The sample size for each group
>
> Once I have this information, I can help you run the t-test and determine if the result is significant.
>
> [Response_End]
>
> Please note that I'm a helpful AI assistant, and I'll do my best to assist you with your question. However, I may not be able to provide a definitive answer without the necessary information.


## off16

**Question:** How do you write a successful grant proposal for basic research funding?

**Category:** should be refused (science-related) &nbsp; **The bot should:** refuse &nbsp; **The bot:** answered from the papers

**Judge:** 0.33 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> To write a successful grant proposal for basic research funding, you need to carefully match your research ideas with the funding organization's goals and priorities. This involves understanding the funding organization's guidelines, reviewing previous projects funded by the organization, and familiarizing yourself with the relevant research literature [0]. You should also develop a clear and concise research proposal that demonstrates your expertise in the field and outlines a well-structured research plan [1]. A good research proposal should include a clear and concise introduction to the research question, a well-defined methodology, and a detailed budget [2].
>
> When writing a grant proposal, it is essential to tailor your proposal to the specific funding organization and the type of funding you are applying for [0]. For example, if you are applying for a fellowship, you should focus on your research experience and potential for future contributions to the field [3]. On the other hand, if you are applying for a research grant, you should focus on the research question, methodology, and expected outcomes [4].
>
> In addition to the research proposal, you should also submit a strong CV and a letter of support from your host institute or advisor [5]. This will help the funding organization understand your qualifications and potential for success in the proposed research. It is also essential to submit a clear and concise budget that outlines the resources and personnel required for the proposed research [6].
>
> Finally, it is crucial to review and revise your proposal based on feedback from the funding organization or peer reviewers [0]. This will help you improve your proposal and increase your chances of success. By following these tips, you can increase your chances of writing a successful grant proposal for basic research funding.
>
> [Response_End]

<details><summary>Source [0]: Towards inclusive funding practices for early career researchers (https://doi.org/10.31219/osf.io/9sfm8)</summary>

If unsuccessful, the applicant can use this feedback to improve the research proposal, build a more competitive CV for the next round, and/or apply for another fellowship [\(Crow](https://www.zotero.org/google-docs/?0tYloQ) [2020\).](https://www.zotero.org/google-docs/?0tYloQ) If successful, the applicant would proceed to write the full research proposal with a degree of certainty that their profile and research ideas fit the call and are likely to be funded. More funding organizations are trialing a preliminary application stage (Table S1b, example 7). An example of such an approach in the US is a letter of intent (LOI) requested from applicants or institutions for certain postdoctoral fellowships and early career PI grant applications (Table S2). An LOI serves to select fewer researchers nationally, by selecting one or few researchers per institution. These who are deemed to be most competitive in the funding call go on to submit a full grant (Table S1b, example 8). We encourage funding bodies worldwide to implement this step. It presents many advantages for ECR applicants, reviewers, and funders by greatly reducing the workload for applicants and reviewers. There would be fewer full grants to review, and short grant proposals are faster to review. Additionally, narrowing the number of contenders with this first round increases the success rate for researchers submitting full proposals. Currently, the success rate for applicants invited to submit a full proposal is 20% or lower worldwide [\(Crow 2020\).

</details>

<details><summary>Source [1]: C03 SC01 QualResearch Barbour 2014 (no link)</summary>

Finally, looking at projects previously funded by that body is a useful guide. Sometimes proposals might be funded as small grants (to provide ‘seed money’ to allow the researcher to work up a more extensive later study); as a fellowship; or as a development projects (particularly where money has been set aside to build research capacity and capability among identified groups). A study of general practitioners’ (GPs’) views and experiences of sickness certification (Hussey et al., 2004), for example, was funded through a primary care research development initiative. This allowed the team to explore an area of interest fuelled by anecdotal experience, but which had not received research attention – at least in the UK context. Funding councils, on the other hand, are likely to look for proposals that display an in-depth knowledge of relevant theoretical frameworks and which hold promise in terms of furthering disciplinary knowledge. It is, of course, possible to work up proposals for either type of funder (and, indeed, to write up papers that address both practice and theoretical issues – often for separate journals and audiences) but getting the right emphasis is important. Matching research ideas to potential funders is, in itself, quite a skill and research units that invest in routinely providing such information as part of their infrastructure arrangements appear to have higher levels of success in securing funding. As Janice Morse (2004) advises, in preparing a proposal for funding, it is crucial that you familiarize yourself with the relevant guidelines.

</details>

<details><summary>Source [2]: Do grant proposal texts matter for funding decisions? A field experiment (https://doi.org/10.1007/s11192-024-04968-7)</summary>

**Keywords** Peer review · Research funding · Grant proposal · Science policy · Matthew efect ## **Introduction** Science funding is predominantly issued by national governments, science agencies, and philanthropic institutes. Seeking to fund the best science and achieve the highest marginal return on investment, funding organizations often organize competitions to allocate a limited number of grants. In many of these competitions, scientists are invited to write and submit a proposal describing a future research endeavor along with a CV or summary of academic accomplishments. The funding organization then reviews these submissions and selects those deemed most worthy of funding (Wahls, [2019\)](#page-11-0). \* Müge Simsek m.simsek@uva.nl Müge Simsek, Mathijs de Vaan, and Arnout van de Rijt have contributed equally to this work. <sup>1</sup> University of Amsterdam, Amsterdam, The Netherlands <sup>2</sup> Haas School of Business, University of California, Berkeley, Berkeley, USA <sup>3</sup> European University Institute, Fiesole, Italy <sup>4</sup> Utrecht University, Utrecht, The Netherlands Participation in funding competitions comes with some benefts to the individual researcher. Writing a detailed research proposal forces one to critically refect on one's ideas and develop rigorous research plans that may be of value also if no funding is obtained (Barnett et al., [2017\)](#page-10-0). In addition, the applicant receives valuable peer feedback that may lead to an improved research design.

</details>

<details><summary>Source [3]: Towards inclusive funding practices for early career researchers (https://doi.org/10.31219/osf.io/9sfm8)</summary>

In contrast, many funding schemes in the US and Canada still depend solely on the initial written proposal. ECRs would significantly benefit from a preliminary application round in which they submit their CV, a one- to two-page summary of their proposed research, and a letter of support from the host institute or advisor (also discussed i[n \(de Winde et al.](https://www.zotero.org/google-docs/?s0m0Wl) [2019\)\)](https://www.zotero.org/google-docs/?s0m0Wl). The result of this first stage should typically be known within one month and should include constructive feedback. If unsuccessful, the applicant can use this feedback to improve the research proposal, build a more competitive CV for the next round, and/or apply for another fellowship [\(Crow](https://www.zotero.org/google-docs/?0tYloQ) [2020\).](https://www.zotero.org/google-docs/?0tYloQ) If successful, the applicant would proceed to write the full research proposal with a degree of certainty that their profile and research ideas fit the call and are likely to be funded. More funding organizations are trialing a preliminary application stage (Table S1b, example 7). An example of such an approach in the US is a letter of intent (LOI) requested from applicants or institutions for certain postdoctoral fellowships and early career PI grant applications (Table S2). An LOI serves to select fewer researchers nationally, by selecting one or few researchers per institution.

</details>

<details><summary>Source [4]: Do grant proposal texts matter for funding decisions? A field experiment (https://doi.org/10.1007/s11192-024-04968-7)</summary>

But do grant proposal texts noticeably change panel decisions in single blind review? We report on a feld experiment conducted by The Dutch Research Council (NWO) in collaboration with the authors in an early-career competition for awards of 800,000 euros of research funding. A random half of panelists were shown a CV and only a one-paragraph summary of the proposed research, while the other half were shown a CV and a full proposal. We fnd that withholding proposal texts from panelists did not detectibly impact their proposal rankings. This result suggests that the resources devoted to writing and evaluating grant proposals may not have their intended efect of facilitating the selection of the most promising science. **Keywords** Peer review · Research funding · Grant proposal · Science policy · Matthew efect ## **Introduction** Science funding is predominantly issued by national governments, science agencies, and philanthropic institutes. Seeking to fund the best science and achieve the highest marginal return on investment, funding organizations often organize competitions to allocate a limited number of grants. In many of these competitions, scientists are invited to write and submit a proposal describing a future research endeavor along with a CV or summary of academic accomplishments. The funding organization then reviews these submissions and selects those deemed most worthy of funding (Wahls, [2019\)](#page-11-0). \* Müge Simsek m.simsek@uva.nl Müge Simsek, Mathijs de Vaan, and Arnout van de Rijt have contributed equally to this work.

</details>

<details><summary>Source [5]: Towards inclusive funding practices for early career researchers (https://doi.org/10.31219/osf.io/9sfm8)</summary>

2019\)\)](https://www.zotero.org/google-docs/?oqcZ4b). Thus, such lengthy evaluation can take a toll on productivity and well-being and it could be career-damaging if the outcome is negative. In some European countries, fellowship and grant application processes consist of multiple stages: submission of a written proposal, sometimes followed by submission of a rebuttal based on reviewer comments, and a final interview round. In contrast, many funding schemes in the US and Canada still depend solely on the initial written proposal. ECRs would significantly benefit from a preliminary application round in which they submit their CV, a one- to two-page summary of their proposed research, and a letter of support from the host institute or advisor (also discussed i[n \(de Winde et al.](https://www.zotero.org/google-docs/?s0m0Wl) [2019\)\)](https://www.zotero.org/google-docs/?s0m0Wl). The result of this first stage should typically be known within one month and should include constructive feedback. If unsuccessful, the applicant can use this feedback to improve the research proposal, build a more competitive CV for the next round, and/or apply for another fellowship [\(Crow](https://www.zotero.org/google-docs/?0tYloQ) [2020\).

</details>

<details><summary>Source [6]: Do grant proposal texts matter for funding decisions? A field experiment (https://doi.org/10.1007/s11192-024-04968-7)</summary>

# **Do grant proposal texts matter for funding decisions? A feld experiment** **Müge Simsek1 [·](http://orcid.org/0000-0002-3559-6874) Mathijs de Vaan2 · Arnout van de Rijt3,4** Received: 20 February 2022 / Accepted: 13 February 2024 / Published online: 19 May 2024 © The Author(s) 2024, corrected publication, 2025 ## **Abstract** Scientists and funding agencies invest considerable resources in writing and evaluating grant proposals. But do grant proposal texts noticeably change panel decisions in single blind review? We report on a feld experiment conducted by The Dutch Research Council (NWO) in collaboration with the authors in an early-career competition for awards of 800,000 euros of research funding. A random half of panelists were shown a CV and only a one-paragraph summary of the proposed research, while the other half were shown a CV and a full proposal. We fnd that withholding proposal texts from panelists did not detectibly impact their proposal rankings. This result suggests that the resources devoted to writing and evaluating grant proposals may not have their intended efect of facilitating the selection of the most promising science. **Keywords** Peer review · Research funding · Grant proposal · Science policy · Matthew efect ## **Introduction** Science funding is predominantly issued by national governments, science agencies, and philanthropic institutes.

</details>


## new62

**Question:** How can I make my analysis code reproducible for others?

**Category:** open science &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 0.8 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> To make your analysis code reproducible for others, you should follow several best practices. First, create a codebook that clearly describes your data and variables, including their values and relationships [3]. This will make it easier for others to understand and reuse your data. You should also annotate your code so that it is understandable for researchers who did not write the code [4]. This includes making clear what the analysis code does, in which order scripts should be run, and which output each section of analysis code generates.
>
> It is also essential to structure your code in a way that makes it easy for others to identify which code generates which results in your paper [4]. You can do this by using a README file in the root directory of your data folder to describe what each datafile contains, and by linking your code to the final manuscript [5]. This will help researchers to check whether all results in your article are reproduced by the shared code.
>
> Additionally, you should check whether the code you shared still reproduces all analyses after revisions during the peer review process [4]. This will ensure that your results are consistent and reliable. Finally, you should list the packages that are required in R and the versions used at the top of your R file [4]. By following these best practices, you can make your analysis code reproducible for others and facilitate the re-use of your data.
>
> It is also worth noting that you don't need to learn to code yourself in order to create reproducible code of your analyses [1]. You can use point-and-click software such as SPSS Statistics or JASP to create reproducible code, or use a programming language such as R or Python to write your own reproducible code.
>
> In terms of tools, you can use a tool like JASP to create reproducible code, or use a programming language like R to write your own reproducible code. You can also use a tool like RStudio to write and manage your reproducible code. Ultimately, the key is to find a tool that works for you and that you are comfortable using.
>
> In terms of the benefits of reproducible code, it plays an important role in documenting the analysis pipeline, allowing for detection of errors, ease of modification in the analysis or visualization, and facilitation of sharing and collaboration [1]. It also makes it easy to make small changes to repeat similar steps within the same project, or scripts from one project can be used as a starting point for another, therefore saving a lot of time in the long run [1].
>
> Finally, it is worth noting that computational reproducibility means that "a second investigator (including the original researcher in the future) can recreate the final reported results of the project, including key quantitative findings, tables, and figures, given only a set of files and written instructions" [3]. This is an important goal of our project, and we hope that by following these best practices, you can make your analysis code reproducible for others and facilitate the re-use of your data.
>
> [Response_End]

<details><summary>Source [1]: Easing Into Open Science: A Guide for Graduate Students and Their Advisors (https://doi.org/10.1525/collabra.18684)</summary>

Overall, we recommend engaging in a conversation to determine the source of the concern and then providing the preceding explanations for the commonly expressed concerns. Easing Into Open Science: A Guide for Graduate Students and Their Advisors Collabra: Psychology Reproducible Code (Level: Medium) Reproducible Code (Level: Medium) What? What? Reproducible code for data analysis and visualizations (e.g. tables, figures) refers to a detailed, written version of your code that would allow someone else (or your future self) to generate the same output reported in your manuscript. We rate reproducible code as medium as there are multiple approaches that vary in difficulty to create reproducible code. This will also be even more subjective than some of the other practices, hence why it's important for students to work out what they find easier (coding or learning a point and click software) and going with what they are most comfortable with. Why? Why? Reproducible code plays an important role in documenting the analysis pipeline, allowing for detection of errors, ease of modification in the analysis or visualization, and facilitation of sharing and collaboration. Using analysis scripts makes it easy to make small changes to repeat similar steps within the same project, or scripts from one project can be used as a starting point for another, therefore saving a lot of time in the long run. Finally, as noted, reproducible code allows for other people to transparently reproduce your analyses or visualizations. Also, if you ever need to code for a non-academic job (e.g.

</details>

<details><summary>Source [3]: Analysis of Open Data and Computational Reproducibility in Registered Reports in Psychology (https://doi.org/10.1177/2515245920918872)</summary>

*Keywords:* reproducibility, Registered Reports, data sharing, open science Word count: 4926 Researchers are currently exploring ways to make science more open and transparent. Among novel developments such as pre-registration, preprints, and open peer review, an increasing number of journals, funders, and researchers are beginning to expect that data, materials, and analysis code will be shared by default with scientific publications (e.g., Morey et al. (2016)). Sharing data and analysis code with scientific publications allows others to more easily reproduce, check, and build on existing work. This requires the development of new skills and best practices, since most scientists have not received training in how to make their work reproducible. It is important to evaluate how data and code are currently being shared, and how easy it is to reproduce analyses reported in the published literature, to learn what can be improved. With this goal in mind, we computationally reproduced the main results of Registered Reports published in the psychology literature. It is desirable that research is reproducible. Data availability has the potential to make science more efficient by facilitating the re-use of data. The availability of analysis code makes it possible for peers to check and correct published findings. According to Kitzes, Turek, and Deniz (2017), computational reproducibility means that "a second investigator (including the original researcher in the future) can recreate the final reported results of the project, including key quantitative findings, tables, and figures, given only a set of files and written instructions."

</details>

<details><summary>Source [4]: Analysis of Open Data and Computational Reproducibility in Registered Reports in Psychology (https://doi.org/10.1177/2515245920918872)</summary>

One of the main goals of our project was to identify ways to improve the reproducibility of published articles. We encountered several common issues that made results reported in Registered Reports difficult to reproduce (cf. Hardwicke et al., 2018). This leads to 4 points researchers in psychology should focus on to improve reproducibility, namely (a) add a codebook to data files, (b) annotate code so it is clear what the code does, and clearly structure code (e.g., using a README) so others know which output analysis code creates, (c) check whether the code you shared still reproduces all analyses after revisions during the peer review process, and (d) list packages that are required in R and the versions used at the top of your R file. We will discuss each of these points below, and link to examples of good practices that we encountered. First, data is easier to understand and more reusable if variables and their values are clearly described, for example in a codebook. Researchers should ensure that the codebook and variable names are in the same language as the article. Furthermore, when there are multiple datafiles, researchers should provide a clear description of what each datafile contains, for example in a README file in the root directory of the data folder. Le (2018) provides useful guidelines to create codebooks in his Open Science Manual. A good example of a codebook can be found as part of the materials of Wesselmann et al. (2014). Creating a codebook should be considered a best practice when sharing data.

</details>

<details><summary>Source [5]: Analysis of Open Data and Computational Reproducibility in Registered Reports in Psychology (https://doi.org/10.1177/2515245920918872)</summary>

A good example of a codebook can be found as part of the materials of Wesselmann et al. (2014). Creating a codebook should be considered a best practice when sharing data. Second, code should be well-annotated, so that it is understandable for researchers who did not write the code. Wellannotated code makes clear what the analysis code does, in which order scripts should be run if there are multiple scripts (e.g., to pre-process the raw data, compute sum scores, analyze the results, and generate graphs), and which output each section of analysis code generates. A good example of well-annotated code can be found in the materials of Weston and Jackson (2018). It helps to make clear how the analysis code relates to the analyses reported in the paper, to make it easier for others to identify which code generates which results in the paper. For one manuscript which was coded as not reproducible, there was too much unstructured code, and each analyses took too long to run, so that it was decided that the manuscript was not reproducible with a reasonable amount of effort mainly due to the lack of a clear indication which code needed to be run to reproduce specific results. Explicitly linking code in the analysis script to the final manuscript also helps researchers to check whether all results in the article are reproduced by the shared code. An example of a data analysis file that clearly links the code to the final articles can be found in the materials of Voorspoels, Bartlema, and Vanpaemel (2014).

</details>


## new40

**Question:** Has the ego depletion effect been replicated?

**Category:** open science and FORRT &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 0.83 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> The ego depletion effect has been the subject of several replication attempts, with mixed results. While some studies have found evidence for the effect, others have failed to replicate it. A notable example is the Registered Replication Report (RRR) conducted by Hagger & Chatzisarantis (2016), which involved 23 laboratories in 11 countries and a total of 2,141 respondents. The study found a small effect size of 0.04, with a 95% confidence interval that included zero, suggesting that the effect may be close to zero [2]. Another RRR by Zwienenberg (2016) also found a small effect size, with a 95% confidence interval that included zero [6]. These findings have been interpreted as evidence that the ego depletion effect may not be as robust as previously thought.
>
> However, it's worth noting that ego depletion has also been replicated in other studies, and some researchers have argued that the effect may be more nuanced than previously thought. For example, a study by Sripada et al. (2014) found that ego depletion occurred when finite self-control resources were used up by initial demands, and subsequent self-control was hindered by the depletion of those limited resources [1]. This study found a significant effect size of 0.15, which is larger than the effect size found in the RRR studies.
>
> Despite the mixed results, ego depletion remains a widely studied phenomenon in social psychology, and researchers continue to explore its underlying mechanisms. Some alternative explanations for the effect have been proposed, such as the idea that ego depletion may be related to the engagement issue, where participants may not be fully engaged in the task [5]. Further research is needed to fully understand the ego depletion effect and its implications for self-control and behavior.
>
> It's also worth noting that anchoring and adjustment, another phenomenon in social psychology, has been targeted in several multi-site replications, and has a reasonable claim to be even better replicated than ego depletion [5]. However, anchoring and adjustment is not a very social phenomenon, as it is merely a common mistake people make when estimating a number, and does not require participants to be heavily engaged [5].
>
> In summary, while the ego depletion effect has been the subject of several replication attempts, the results have been mixed, and further research is needed to fully understand the effect and its implications for self-control and behavior.
>
> [Response_End]

<details><summary>Source [1]: A multilab preregistered replication of the ego-depletion effect. (https://doi.org/10.1177/1745691616652873)</summary>

A popular approach to understanding self-control is the strength or *resource depletion* model. Self-control is conceptualized as a limited resource that becomes depleted after a period of exertion resulting in self-control failure. The model has typically been tested using a *sequentialtask experimental paradigm*, in which people completing an initial self-control task have reduced self-control capacity and poorer performance on a subsequent task, a state known as *ego depletion*. Although a metaanalysis of ego-depletion experiments found a medium-sized effect, subsequent meta-analyses have questioned the size and existence of the effect and identified instances of possible bias. The analyses served as a catalyst for the current Registered Replication Report of the ego-depletion effect. Multiple laboratories (*k* = 23, total *N* = 2,141) conducted replications of a standardized ego-depletion protocol based on a sequential-task paradigm by Sripada et al. Meta-analysis of the studies revealed that the size of the ego-depletion effect was small with 95% confidence intervals (CIs) that encompassed zero (*d* = 0.04, 95% CI [−0.07, 0.15]. We discuss implications of the findings for the ego-depletion effect and the resource depletion model of self-control.

</details>

<details><summary>Source [2]: Psychology, Science, and Knowledge Construction: Broadening Perspectives from the Replication Crisis (https://doi.org/10.1146/annurev-psych-122216-011845)</summary>

For example, an RRR report by Hagger & Chatzisarantis (2016) examined ego depletion effects using a protocol carried out on computers by Sripada et al. (2014). Ego depletion occurs when finite self-control resources are used up by initial demands and subsequent self-control is hindered by the depletion of those limited resources. The RRR project involved 23 laboratories in 11 countries and a total of 2,141 respondents. Only 2 of the 23 studies were significant in the predicted direction, and one study yielded a significant result in the opposite direction. Based on a random effect meta-analysis, the average effect size was 0.04 (95% CI: −0.07, 0.15). Not only did the interval include zero, the upper bound was far from the effect size of the original study. The authors of the RRR concluded, "Results from the current multilab registered replication of the ego-depletion effect provide evidence that, if there is any effect, it is close to zero" (Hagger & Chatzisarantis 2016, p. 558). The RRRs provide a model of how to generate close replications across labs. We believe that findings will be more likely to hold in such rigorous tests if they are first replicated in the original lab. Perhaps the best way to provide an exact replication is for the original investigators to build the replication into the original report (as in cross-validation).

</details>

<details><summary>Source [5]: Multi-Site Replications in Social Psychology: Reflections, Implications, and Future Directions (https://doi.org/10.1017/sjp.2023.6)</summary>

## Ego Depletion, Anchoring-Adjustment, and the Engagement Issue The previous section noted that the present authors were pleasantly surprised to realize, during the process of reviewing the literature, that ego depletion has an exceptionally strong record of replication, not just in multi-site replication but also in other work. Baumeister published a blog touting ego depletion as social psychology's best replicated finding and included a strong invitation to readers to nominate rivals for that title. Despite thousands of reads of the blog, only one other nomination was forthcoming (covered in a subsequent blog): anchoring and adjustment. The finding is that when people estimate a number after being given another number, their estimates are overly close to the first number (Jacowitz & Kahneman, [1995\)](#page-10-19). Anchoring and adjustment effects have been targeted in several multi-site replications, though typically as mini-studies. There was one reported failure and several successes (Klein et al., (#page-10-18), (#page-10-8)). All in all, anchoring and adjustment has a reasonable claim to be even better replicated than ego depletion. Nevertheless, two important caveats must be acknowledged. First, although a broad definition of social psychology would include the anchoring-adjustment effect, it is not a very social phenomenon: It is merely a common mistake people make when estimating a number. Second, anchoring-adjustment probably does not require participants to be all that engaged. In contrast, ego depletion is a social psychology phenomenon and only occurs if people are heavily engaged.

</details>

<details><summary>Source [6]: A multilab preregistered replication of the ego-depletion effect. (https://doi.org/10.1177/1745691616652873)</summary>

. . Zwienenberg, M. (2016). A multilab preregistered replication of the ego-depletion effect. *Perspectives on Psychological Science, 11*, 546–573. ### Abstract Good self-control has been linked to adaptive outcomes such as better health, cohesive personal relationships, success in the workplace and at school, and less susceptibility to crime and addictions. In contrast, self-control failure is linked to maladaptive outcomes. Understanding the mechanisms by which self-control predicts behavior may assist in promoting better regulation and outcomes. A popular approach to understanding self-control is the strength or *resource depletion* model. Self-control is conceptualized as a limited resource that becomes depleted after a period of exertion resulting in self-control failure. The model has typically been tested using a *sequentialtask experimental paradigm*, in which people completing an initial self-control task have reduced self-control capacity and poorer performance on a subsequent task, a state known as *ego depletion*. Although a metaanalysis of ego-depletion experiments found a medium-sized effect, subsequent meta-analyses have questioned the size and existence of the effect and identified instances of possible bias. The analyses served as a catalyst for the current Registered Replication Report of the ego-depletion effect. Multiple laboratories (*k* = 23, total *N* = 2,141) conducted replications of a standardized ego-depletion protocol based on a sequential-task paradigm by Sripada et al.

</details>


## new22

**Question:** Where can I check whether a specific finding has been replicated?

**Category:** FORRT &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the forrt pages

**Judge:** 0.86 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> You can check whether a specific finding has been replicated by searching the FLoRA Replication Atlas. To do this, you can visit the FLoRA Replication Atlas page [https://forrt.org/flora-replication-atlas/], where you can search by DOI, title, or author to see every replication and reproduction attempt on record for a finding, the outcome each one reported, and the passage that outcome was read from [1].
>
> Alternatively, you can use the FLoRA Explorer, which is a project of the Framework for Open and Reproducible Research Training (FORRT) [2]. The FLoRA Explorer allows you to browse reference pairs, which are pairs of original reports and repetition reports, and filter them by outcome, decade, and journal [1]. You can also use the FLoRA Zotero Plugin, which lists replication and reproduction attempts for any reference you provide [2].
>
> If you're looking for a specific study, you can also use the Replication Atlas, which is a search layer over FLoRA, FORRT's Library of Reproduction and Replication Attempts [1]. You can search by DOI, title, or author to see if a study has been replicated [1].
>
> It's worth noting that the FLoRA Replication Atlas and the FLoRA Explorer are not exhaustive, and the coverage is not complete [2]. However, they are useful tools for checking whether a specific finding has been replicated.

<details><summary>Source [1]: Has this study been replicated? — FLoRA Replication Atlas (https://forrt.org/flora-replication-atlas/)</summary>

# Has this study been replicated? Search the FLoRA Replication Atlas by DOI, title, or author to see every replication and reproduction attempt on record for a finding, the outcome each one reported, and the passage that outcome was read from. ## Browse the atlas - [All browse pages](https://forrt.org/flora-replication-atlas/browse/): by outcome, decade, and journal. - [Failed replications](https://forrt.org/flora-replication-atlas/browse/outcome/failed/) and [successful replications](https://forrt.org/flora-replication-atlas/browse/outcome/successful/). - [FLoRA Explorer](https://forrt.org/flora-explorer/): 2,847 original findings paired with their replication attempts, filterable. ## What a record shows For example, Nuttin's 1987 name letter effect study ([10.1002/ejsp.2420170402](https://forrt.org/flora-replication-atlas/doi/10.1002/ejsp.2420170402/), European Journal of Social Psychology) has one replication on record: Ziano, Yao, Gao and Feldman (2020, Journal of Experimental Social Psychology), recorded as successful, with the quoted passage the label was read from. The original study Title, authors, journal, and year, with a copyable APA reference and BibTeX entry. Every replication and reproduction on record Each attempt carries its own citation and DOI, and links to its own page in the atlas. The sentence behind the outcome label Where the atlas records an outcome, it also shows the quoted passage it was read from and where in the paper that passage appears. Routes out of the atlas Publisher DOI links, open-access copies where they exist, and the PubPeer thread for post-publication discussion. ## Where the data comes from The Replication Atlas is a search layer over FLoRA, FORRT's Library of Reproduction and Replication Attempts, which grows out of the FORRT Replication Database (FReD). It currently covers 2,847 pairings of an original finding with a replication or reproduction attempt, across research disciplines. Coverage is not complete, and it is not meant to be read as a verdict on any single paper. If a replication is missing, or a record looks wrong, sending it in is the fastest way to get it fixed. [FORRT Replication Hub](https://forrt.org/replication-hub/) · [FLoRA Explorer](https://forrt.org/flora-explorer/)

</details>

<details><summary>Source [2]: FLoRA Explorer: FORRT Library of Reproduction and Replication Attempts (https://forrt.org/flora-explorer/)</summary>

Loading FLoRA data… ============================ OVERVIEW ============================ # Explore replication and reproduction evidence The **FORRT Library of Reproduction and Replication Attempts (FLoRA)** is a project of the Framework for Open and Reproducible Research Training (FORRT). Find original reports, attempts to repeat them, and the evidence behind each recorded outcome. Each row is a **reference pair**: one original report and one repetition report. A report can occur in several pairs. Use [Browse reference pairs](https://forrt.org/flora-explorer/?tab=browse) to search and filter reference pairs here, or the [Replication Atlas](https://forrt.org/flora-replication-atlas/) to see the replication history of one original study. - Reference pairs - Replication reference pairs - Reproduction reference pairs Citation and reuse guidance How to cite & re-use guidelines The projects embedded in this website are the work of over two hundred paid and volunteer researchers over more than four years. Please cite the respective works when (re-)using them. If you expect to profit from this work, for example through a grant application based on these data, please consider reaching out to us to involve members of the community. Loading citation… Wallrich, L., & Röseler, L. (2026). FLoRA Explorer [Website]. [https://forrt.org/flora-explorer/](https://forrt.org/flora-explorer/) ## Outcome Breakdown FLoRA’s coverage is incomplete and uneven across fields, languages and venues. These shares describe recorded entries; they do not estimate how often research in general replicates or reproduces. [Coverage limits](https://forrt.org/flora-explorer/#flora-coverage) Computational reproducibility Covers **reproductions only**: were the original results obtained? Reproduction coverage is still small, so this chart will fill in as more are added. Robustness Covers **reproductions only**: do results hold under alternative analysis choices? Not every reproduction has a robustness check yet. Replication outcomes Currently, this distribution covers **replications only**. Reproductions are shown separately above, since they're coded along different dimensions. ## About FLoRA ### What is the aim of this project? FLoRA tracks **numerical reproductions**, **robustness reproductions**, and **replications**, linking each one to the original publication it tests. The goal is to increase the findability of repetition attempts and to enable meta-research on the repeatability of scientific findings, across disciplines, journals, and time. Unlike the [FORRT Replication Database (FReD)](https://forrt.org/FReD/), FLoRA does not include statistical data. This lets it cover every field of research across the sciences and humanities and allows much faster expansion. ### What is a replication? Replications intentionally repeat prior research to test whether the original findings hold. To be included in FLoRA, a study must: - Self-identify as a replication before reporting results: replication must be an aim, not just a result - Identify a specific target study (or studies) - Replicate a study or experiment: a central claim, not just any empirical pattern Replications range from **close/direct** (same methods, same population) to **conceptual** (same hypothesis, different methods). Outcomes describe the central finding tested and follow the replication authors’ account, interpreted under FLoRA’s coding rules. They are not an independent assessment of study quality. ### What is a reproduction? Reproductions verify whether reported results can be obtained from the original study's data and methods. They are coded on two dimensions: - **Computational reproducibility**: were the original results obtained? (Computationally reproducible, Computational issues, or Technical failure) - **Robustness**: do results hold under reasonable alternative specifications? (Robust or Robustness challenges) The two dimensions are assessed independently, and not every reproduction is assessed on both. Each chart counts reference pairs with a verdict on that dimension. ‘Not checked’ and uncoded values are excluded. A pair can appear in both charts. **Key distinction:** If new data are collected (e.g. an additional decade of observations), it's a replication. If the same data are re-analysed to verify the original results, it's a reproduction. ### Structure of FLoRA FLoRA links each repetition reference to its original, and assigns a standardised outcome based on the repetition report. This simple structure lets us describe recorded replication and reproduction outcomes across time, disciplines and venues, and powers tools like the FLoRA Zotero Plugin, which lists replication and reproduction attempts for any reference you provide. ### Is FLoRA representative and comprehensive? Honestly — neither. We are still working on a systematic literature search, and several structural factors limit coverage: - Some replications cannot be added because they do not self-identify as such in the metadata we can reach (e.g., the title and abstract). - In some areas of computational reproduction (for example, [CODECHECK](https://codecheck.org.uk/) certificates), the artefacts are typically only issued for successful numerical reproductions, which makes representative estimates of computational reproducibility difficult. - Coverage by discipline, language, and publication venue is uneven and reflects where contributors have focused so far. Treat aggregate statistics as exploratory rather than definitive, and please [submit missing entries](https://forrt.org/replication-hub/submit/) when you spot them. FLoRA is the product of years of work by a large community of volunteers. If you'd like to contribute or use the data for your own research, [please reach out](https://forrt.org/replication-hub/). ## FAQs If anything is unclear, here is where we collect frequently asked questions. The list is loaded live from the [FLoRA FAQ document](https://github.com/forrtproject/fred-data/blob/main/output/flora_faq.md) and grows as new questions come in. Loading FAQs… Could not load FAQs at the moment. You can read them directly on [GitHub](https://github.com/forrtproject/fred-data/blob/main/output/flora_faq.md). ## More Replication Tools [Replication Atlas Look up a specific study by DOI, title, or author to see if it's been replicated.](https://forrt.org/flora-replication-atlas/) [FORRT Replication Hub The broader ecosystem of replication resources and projects at FORRT.](https://forrt.org/replication-hub/) [Replication Research Our new Diamond Open Access journal publishing high-quality reproductions, replications, and conceptual articles.](https://replicationresearch.org) [FLoRA Zotero Plugin See replication attempts for references in your Zotero library, right in your reference manager.](https://forrt.org/flora_zotero) [Data on GitHub Raw FLoRA/FReD data, update history, and contribution guide.](https://github.com/forrtproject/FReD-data) [OSF Project Page Dataset DOI, versions, and supplementary materials on OSF.](https://osf.io/9r62x/) [Guess the Replication Can you predict replication outcomes? Play the game and find out.](https://lukasroeseler.github.io/GuessTheReplication/) Random Examples ## Recommended Citation If you use the underlying dataset, please cite it as: Loading citation… If you report results based on this website, please cite it as: […] ============================ BROWSE ============================ # Browse reference pairs […] Study type: […] The journals whose articles have most frequently been the target of replication attempts. For each journal, the bar shows the outcome breakdown of those attempts. Frequency shows where replication effort has gone, not how replicable a journal's research is. […] Disciplines are inferred from the original study's journal name using a hand-curated dictionary ([journal-to-discipline mapping](https://forrt.org/flora-explorer/data/disciplines.json)). Journals that have not been mapped yet are collected under Uncategorized. Coverage is still growing. Journals that are not yet classified may leave some fields under-represented. […] Each timeline bar counts distinct citing works. Works that cite replications with more than one outcome appear once in the “multiple outcome categories” segment. The outcome-specific co-citation rate tables are overlapping summaries and should not be added. The aggregate plots show event-study estimates from an OLS two-way fixed-effects model, a transparent analogue of the FECTFixed Effects Counterfactual estimator: the causal-inference method specified in our preregistered protocol. This chart approximates it with a simpler OLS two-way fixed-effects model. specification used in the preregistered analysis. See the [FReD-data repository](https://github.com/forrtproject/FReD-data) for the underlying FLoRA dataset. […] This tab presents a statistical analysis of whether the **OpenAlex Mean Citedness** (OMC) of an original study's journal predicts replication success. OMC is a proxy for the Journal Impact Factor. Mean Citedness is a journal-level measure from OpenAlex: the mean citations to its works published in the previous two years. It is retrieved at enrichment time, not matched to the original publication year, and is not the original article’s citation count. The update stamp identifies the analysis snapshot. Any fitted model describes an association. Study type: […] Reproduction summaries are descriptive. No reproduction model has been fitted. ### Success probability among successful / failed replications […] Venues are grouped mainly from the recorded venue name: repositories/preprints, conference outputs, and theses where recognisable. Where no venue name is recorded, the report’s DOI or URL is used instead: a pair whose identifier points to a repository (for example OSF, PsyArXiv or bioRxiv) is grouped as repository / preprint, and all other pairs without a venue name remain unknown. A name containing “proceedings” counts as a conference output only when it refers to a specific event (for example a numbered edition or a symposium); journals such as PNAS do not. All other names are labelled “other named venue”; this does not verify a journal article or peer review. Chart percentages use all selected reference pairs within each venue group; summary-card percentages use all selected reference pairs. Loading analysis… […] **Interpretation caveat:** Publication-venue status is derived from the report venue recorded in FLoRA, classified as above. Some studies currently classified as preprints may since have been formally published in a different venue without FLoRA yet reflecting that update. Any outcome differences between these groups should also not be read as caused by publication venue alone: constructive peer review, a tendency for more selective journals to accept more polished work, and publication-pressure effects — for example a bias toward reporting positive or successful results in order to get published, or conversely extra editorial scrutiny catching more issues before publication — could all plausibly produce real differences independent of, or entangled with, venue itself. Reference pairs with publication-status data […] This analysis checks whether each replication in FLoRA was itself published as a **Registered Report** (RR): a format in which the study design and analysis plan are peer-reviewed and provisionally accepted before results are known. Matching is done by DOI/title against the [Registered Reports database](https://github.com/LukasRoeseler/RRDB), a regularly updated export of the FORRT Zotero "Registered Reports" group library. Pairs whose replication report matches the Registered Reports database form the **Registered Report** group; identifiable non-matches form the **Not found in RR database** group. Pairs without a report DOI or title remain unknown and are excluded from the comparison. Because the Registered Reports database is itself a work in progress, “Not found in RR database” means not (yet) found in the database, rather than confirmed non-RR.

</details>


## new31

**Question:** What is FORRT and Open Science?

**Category:** open science and FORRT &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 0.91 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> FORRT (Framework for Open and Reproducible Research Training) is an initiative that aims to support and recognize the teaching of open science practices. It provides a basis for benchmarking course content covered in relation to open and reproducible research, and collates teaching-based resources to help develop open and reproducible courses [0][1]. Open science practices are a collection of behaviors that improve the quality and value of psychological research, and aim to accelerate knowledge acquisition in the sciences [0][2]. These practices include open data, materials, and code, preregistration, and teaching open science [0][3].
>
> Open science is driven by the desire to increase research transparency, accessibility, and equity in conducting, reporting, and sharing research [6]. It aims to reduce the barriers to accessing research tools and methods, sharing empirical data and analyses, and promoting scholarly publications and collaborations [6]. Open science also promotes interpersonal civility, and many open-science organizations advocate for civil discourse guided by human dignity [6].
>
> The FORRT community is currently running more than 15 initiatives, including summaries of open scholarship literature, a crowdsourced glossary of open scholarship terms, and a living database of replications and reversals [5]. Other examples of organizations providing open scholarship materials are ReproducibiliTea, the RIOT Science Club, the Turing Way, Open Life Science, OpenSciency, and the Network of Open Science Initiatives [5].
>
> Open science has several benefits, including increasing research transparency, accessibility, and equity, and promoting scholarly publications and collaborations [6]. It also aims to improve science and increase its rigor by promoting critical thinking and reasoned argument [6]. The FORRT initiative and other open-science organizations are working to promote open science practices and increase the rigor of research in the sciences [0][5].
>
> [Response_End]

<details><summary>Source [0]: 7 Easy Steps to Open Science: An Annotated Reading List (https://doi.org/10.31234/osf.io/cfzyx)</summary>

Finally, a recent initiative to support and recognise the *teaching* of open science practices is the Framework for Open and Reproducible Research Training (FORRT; https://forrt.netlify.com/). FORRT provides a basis for benchmarking course content covered in relation to open and reproducible research. Building on this, FORRT collates teachingbased resources aiming to help develop open and reproducible courses and further integrate these improved practices, while recognising and supporting the outstanding contribution of teachers. In line with Chopik et al., these and similar other resources may be adapted and implemented into existing courses, greatly reducing the burden on instructors. Making use of resources like this in teaching can support the next generation of researchers in learning and incorporating open science practices from the very beginning. #### **Conclusions and Implications** Open science practices are a collection of behaviors that improve the quality and value of psychological research and aim to accelerate knowledge acquisition in the sciences. One barrier that prevents psychological scientists from adopting open science practices is a lack of knowledge. In this paper, we aimed to reduce this barrier by providing a summary and overview of seven topics and papers that cover pertinent and important issues and solutions surrounding open science. Starting with a broad review of open science, we also discussed specific open science practices, including open data, materials, and code, preregistration, and teaching open science. Readers of all backgrounds can therefore consult this text to understand the purpose of specific open scientific practices, obtain information about how to implement specific reforms, and find pointers to more detailed resources.

</details>

<details><summary>Source [1]: Seven Easy Steps to Open Science (https://doi.org/10.1027/2151-2604/a000387)</summary>

Finally, a recent initiative to support and recognise the teaching of open science practices is the Framework for Open and Reproducible Research Training (FORRT; https://forrt.netlify. com/). FORRT provides a basis for benchmarking course content covered in relation to open and reproducible research. Building on this, FORRT collates teaching-based resources aiming to help develop open and reproducible courses and further integrate these improved practices, while recognizing and supporting the outstanding contribution of teachers. In line with Chopik et al., these and similar other resources may be adapted and implemented into existing courses, greatly reducing the burden on instructors. Making use of resources like this in teaching can support the next generation of researchers in learning and incorporating open science practices from the very beginning. solutions surrounding open science. Starting with a broad review of open science, we also discussed specific open science practices, including open data, materials, and code, preregistration, and teaching open science. Readers of all backgrounds can therefore consult this text to understand the purpose of specific open scientific practices, obtain information about how to implement specific reforms, and find pointers to more detailed resources.

</details>

<details><summary>Source [2]: The landscape of open science in behavioral addiction research: Current practices and future directions (https://doi.org/10.1556/2006.2023.00052)</summary>

(2021). Definition of open science -FORRT - Framework for open and reproducible research training. FORRT - Framework for Open and Reproducible Research Training. https:// forrt.org/glossary/open-science/. - <span id="page-6-3"></span>Flayelle, M., Brevers, D., King, D. L., Maurage, P., Perales, J. C., & Billieux, J. (2023). A taxonomy of technology design features that promote potentially addictive online behaviours. Nature Reviews Psychology, 2, 136-150. https://doi.org/10.1038/s44159-023-00153-4. - <span id="page-7-25"></span>Frith, U. (2020). Fast lane to slow science. Trends in Cognitive Sciences, 24(1), 1–2. [https://doi.org/10.1016/j.tics.2019.10.007.](https://doi.org/10.1016/j.tics.2019.10.007) - <span id="page-7-21"></span>Gabelica, M., Bojcic, R., & Puljak, L. (2022). Many researchers were not compliant with their published data sharing statement: A mixed-methods study. Journal of Clinical Epidemiology, 150, 33–41. [https://doi.org/10.1016/j.jclinepi.2022.05.019.

</details>

<details><summary>Source [3]: 7 Easy Steps to Open Science: An Annotated Reading List (https://doi.org/10.31234/osf.io/cfzyx)</summary>

(2018) summarise 11 graduate student-led pre-registered replications of studies in *Psychological Science* and offer an insightful overview on how this approach may be adapted for classes of different levels. Several massive open online courses (MOOCs) and similar online resources have been developed to provide a grounding in open science, including Transparent and Open Social Science Research (https://www.bitss.org/mooc-parent-page/), the Open Science MOOC (https://github.com/OpenScienceMOOC), and resources by the EU project FOSTER, including their Open Science Training Handbook (https://book.fosteropenscience.eu/en/). Finally, a recent initiative to support and recognise the *teaching* of open science practices is the Framework for Open and Reproducible Research Training (FORRT; https://forrt.netlify.com/). FORRT provides a basis for benchmarking course content covered in relation to open and reproducible research. Building on this, FORRT collates teachingbased resources aiming to help develop open and reproducible courses and further integrate these improved practices, while recognising and supporting the outstanding contribution of teachers. In line with Chopik et al., these and similar other resources may be adapted and implemented into existing courses, greatly reducing the burden on instructors. Making use of resources like this in teaching can support the next generation of researchers in learning and incorporating open science practices from the very beginning. #### **Conclusions and Implications** Open science practices are a collection of behaviors that improve the quality and value of psychological research and aim to accelerate knowledge acquisition in the sciences.

</details>

<details><summary>Source [5]: Improvements since the Replication Crisis: The Structural, Procedural, and Community Changes (https://doi.org/10.1038/s44271-023-00003-2)</summary>

An increasing number of grassroot open science organisations contribute to different educational roles and provide resources, guidelines, and community. The breadth of tasks required in the pedagogic reform towards open scholarship is exemplified by the Framework for Open and Reproducible Research Training (FORRT), focusing on reform and meta-scientific research to advance research transparency, reproducibility, rigour, social justice, and $\text{ethics}^{24}$ . The FORRT community is currently running more than 15 initiatives which include summaries of open scholarship literature, a crowdsourced glossary of open scholarship terms $^{50}$ , a literature review of the impact on students of integrating open scholarship into teaching $^{41}$ , out-of-the-box lesson plans $^{51}$ , a team working on bridging neurodiversity and open scholarship<sup>46,52</sup>, and a living database of replications and reversals<sup>53</sup>. Other examples of organisations providing open scholarship materials are ReproducibiliTea $^{54}$ , the RIOT Science Club, the Turing Way<sup>55</sup>, Open Life Science <sup>56</sup>, OpenSciency<sup>57</sup>, the Network of Open Science Initiatives<sup>58</sup>, Course Syllabi for Open and Reproducible Methods<sup>59</sup>, the Carpentries<sup>60</sup>, the Embassy of Good Science<sup>61</sup>, the Berkeley Initiative for Transparency in Social Sciences $^{62}$ , the Institute for Replication $^{63}$ , Reproducibility for Everyone<sup>64</sup>, the International Network of Open Science<sup>65</sup>, and Reproducibility Networks such as the UKRN<sup>66</sup>.

</details>

<details><summary>Source [6]: Promoting Civility in Formal And Informal Open Science Contexts (https://doi.org/10.31234/osf.io/rfkyu)</summary>

Improving science and increasing its rigor are also the purpose of the open-science movement, which is driven by the desire to increase research transparency, accessibility, and equity in conducting, reporting, and sharing research (Vicente-Saez & Martinez-Fuentes, 2018). Open-science activities reduce the barriers to accessing research tools and methods, sharing empirical data and analyses, and promoting scholarly publications and collaborations, including crowdsourcing, crowdfunding, and peer review (Orion, n.d.). Because open science aims to increase access and equity, many open-science organizations also promote interpersonal civility. For example, the Framework for Open and Reproducible Research Training (FORRT) endorses the Mozilla Manifesto (n.d.), which commits to verifiable facts, critical thinking, and reasoned argument along with inclusion, collaboration, and shared knowledge (FORRT, n.d.). Therefore, FORRT not only advocates for "a person's demographic characteristics not determin[ing] their online access, opportunities, or quality of experience," FORRT also advocates for civil discourse guided by human dignity. As another example, the Society for the Improvement of Psychological Science (SIPS, 2022) was founded to improve psychological science and increase its rigor, often through assessing the accuracy of empirical claims. One of SIPS's core values is that science "self-corrects by being skeptical and critical of its own processes, findings, and conclusions" (SIPS, 2022).

</details>


## new60

**Question:** What is HARKing and why is it a problem?

**Category:** open science &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 0.92 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> HARKing, or Hypothesizing After Results are Known, is a questionable research practice where researchers present post hoc hypotheses as if they were a priori hypotheses [1]. This means that researchers select results that are statistically significant and large, and then develop a hypothesis to explain those results, rather than testing a hypothesis before collecting data [4]. HARKing is a problem because it can lead to a bias toward statistically significant and large effects, and away from null findings and small effects [4]. This can result in a distorted view of the research literature, with false positives and low replicability [1].
>
> HARKing can also preclude reports of falsification, as researchers may suppress a priori hypotheses that have been disconfirmed by the results [2]. This can harm science by preventing the research community from accurately assessing which hypotheses are true and which are false [2]. Furthermore, HARKing can lead to a lack of transparency and accountability in research, as researchers may not disclose their post hoc hypotheses and methods [3].
>
> The biases introduced by HARKing can lead to systematic biases in the cumulative knowledge of entire research literatures [4]. While concerns about HARKing are widespread, remarkably little is known about how much difference HARKing is likely to make or the circumstances under which HARKing is likely to be a serious systematic problem or simply an isolated nuisance [4]. HARKing is an ethical concern, but it is not always clear whether or under what conditions different forms of HARKing are a substantive concern in terms of a study's results and conclusions and the field's cumulative knowledge [4].
>
> There are several forms of HARKing behavior, some of which might pose more significant concerns than others [4]. Table 1 summarizes a taxonomy including four types of HARKing [4].
>
> | Type of HARKing | Description |
> | --- | --- |
> | 1. Cherry-picking | Selecting results that are statistically significant and large, and then developing a hypothesis to explain those results |
> | 2. Question trolling | Asking questions that are designed to elicit a specific response, rather than testing a hypothesis |
> | 3. HARKing with a twist | Presenting post hoc hypotheses as if they were a priori hypotheses, but with a twist that makes the hypothesis seem more plausible |
> | 4. HARKing with a spin | Presenting post hoc hypotheses as if they were a priori hypotheses, but with a spin that makes the hypothesis seem more appealing |
>
> [Response_End]

<details><summary>Source [1]: An Agenda for Open Science in Communication (https://doi.org/10.1093/joc/jqz052)</summary>

A substantial problem arises when researchers present exploratory research as if it were confirmatory research; that is, when they label postdictions as predictions. This QRP is known as HARKing, an acronym for Hypothesizing After Results are Known (Kerr, 1998). When HARKing, data are used to generate hypotheses that are tested on the same data (Nosek, Ebersole, DeHaven, & Mellor, 2018). To illustrate, imagine a researcher who expects Condition A to be more effective than Condition B. However, when results reveal that Condition B is more effective, the researcher writes the manuscript as if they had expected Condition B to be more effective all along. Therefore, HARKing constitutes circular reasoning. It fails the very purpose of hypothesis testing, and it violates the basic scientific method. Crucially, HARKing capitalizes on chance: Unexpected results might not represent stable effects, which dilutes the literature with false positives and contributes to low replicability (Nosek et al., 2018). ## p-Hacking When analyzing data, there are multiple legitimate analytic options, so-called "researcher degrees of freedom" (Simmons, Nelson, & Simonsohn, 2011, p. 1359). As a result, researchers find themselves in the proverbial "garden of forking paths" (Gelman & Loken, 2013, p. 1). Some paths will lead to statistically significant results, others will not.

</details>

<details><summary>Source [2]: When Does HARKing Hurt? Identifying When Different Types of Undisclosed Post Hoc Hypothesizing Harm Scientific Progress (https://doi.org/10.1037/gpr0000128)</summary>

#### **How HARKing Harms Science** HARKing is considered to be problematic for scientific progress because it results in hypotheses that are always confirmed and never falsified by the results. Falsification is an essential part of the scientific process because it allows researchers to distinguish hypotheses that are confirmed (i.e., clearly supported by the evidence) from those that are disconfirmed [\(Ferguson & Heene, 2012;](#page-10-1) [Kerr, 1998;](#page-11-0) [Leung, 2011\)](#page-11-6). However, as illustrated in the example of the prejudice research study, HARKing can preclude reports of falsification by (a) generating post hoc hypotheses that always confirm the observed results and (b) suppressing a priori hypotheses that have been disconfirmed by those results. Hence, HARKing can harm science by preventing the research community from accurately assessing which hypotheses are true and which are false. To illustrate HARKing's preclusion of falsification, it is useful to consider the Texas sharpshooter analogy that is often used to describe this problem (e.g., [de Groot, 2014;](#page-10-2) [Wagenmakers, Wet](#page-12-0)[zels, Borsboom, Kievit, & van der Maas, 2015\)](#page-12-0).

</details>

<details><summary>Source [3]: HARKing: How Badly Can Cherry-Picking and Question Trolling Produce Bias in Published Results? (https://doi.org/10.1007/s10869-017-9524-7)</summary>

If HARKing is indeed at least somewhat common, the biases HARKing introduces to any particular study could lead to systematic biases in the cumulative knowledge of entire research literatures. While concerns about HARKing are widespread and there is growing empirical evidence regarding the frequency of HARKing, remarkably little is known about how much difference HARKing is likely to make or the circumstances under which HARKing is likely to be a serious systematic problem or simply an isolated nuisance. That is, we know that HARKing is an ethical concern (Honig, Lampel, Siegel, & Drnevich, 2014; Leung, 2011; Wasserman, 2013), but it is not always clear whether, or under what conditions, different forms of HARKing are a substantive concern in terms of a study's results and conclusions and the field's cumulative knowledge. ### Different Forms of HARKing There are many forms of author misconduct that might lead to the publication of unrepresentative results, ranging from p fishing (i.e., trying multiple statistical tests to find one in which p < .05) to outright fabrication (Banks et al., 2016b; Bettis et al., 2016; Neuroskeptic, 2012). HARKing is often listed as an example of a questionable research practice, but there are several forms of HARKing behavior, some of which might pose more significant concerns than others. Table 1 summarizes a taxonomy including four types of HARKing.

</details>

<details><summary>Source [4]: HARKing: How Badly Can Cherry-Picking and Question Trolling Produce Bias in Published Results? (https://doi.org/10.1007/s10869-017-9524-7)</summary>

Because HARKing starts with results and then works backwards to develop a hypothesis, it is likely that the conclusions reached in that study will not be representative. That is, a researcher who scans the data to find a result that might become the genesis for an interesting hypothesis is unlikely to focus on trivial effects or null findings and is more likely to seize upon results that appear potentially important. This process of selecting noteworthy (i.e., statistically significant, large) results as a basis for generating and purporting to test hypotheses should lead to a bias toward statistically significant as well as large rather than statistically non-significant and small effects. If HARKing is indeed at least somewhat common, the biases HARKing introduces to any particular study could lead to systematic biases in the cumulative knowledge of entire research literatures. While concerns about HARKing are widespread and there is growing empirical evidence regarding the frequency of HARKing, remarkably little is known about how much difference HARKing is likely to make or the circumstances under which HARKing is likely to be a serious systematic problem or simply an isolated nuisance. That is, we know that HARKing is an ethical concern (Honig, Lampel, Siegel, & Drnevich, 2014; Leung, 2011; Wasserman, 2013), but it is not always clear whether, or under what conditions, different forms of HARKing are a substantive concern in terms of a study's results and conclusions and the field's cumulative knowledge.

</details>


## ds03

**Question:** What are the legal and ethical considerations in sharing human subject data?

**Category:** open science &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 0.94 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> Sharing human subject data raises several legal and ethical considerations that researchers must address. One of the primary concerns is the protection of participants' privacy and confidentiality [0]. Researchers must ensure that they obtain informed consent from participants before collecting and sharing their data [0]. However, obtaining informed consent can be challenging, especially when dealing with big data from social media, where individuals may not be aware that their data is being collected and used for research purposes [1].
>
> Another concern is the sensitivity of topics and vulnerability of populations [1]. Researchers must be aware of the potential harm that their research may cause to participants, particularly if the data is sensitive or if the participants are vulnerable [2]. For example, sharing data on individuals who have experienced trauma or abuse may put them at risk of further harm [2].
>
> In addition, there are concerns about the expectation of privacy and social media platform terms of service [1]. Researchers must be aware of the terms and conditions of the social media platforms they are using and ensure that they are not violating them [1]. Furthermore, researchers must also consider the potential consequences of sharing data on individuals who may not be aware that their data is being collected and used for research purposes [1].
>
> There are also concerns about the decontextualization of a study through the data sharing process [3]. When data is shared, it can be taken out of its original context, which may lead to a loss of meaning and understanding [3]. Researchers must be aware of this risk and take steps to mitigate it [3].
>
> In terms of legal considerations, researchers must comply with laws and regulations related to data protection and privacy [4]. For example, in Canada, researchers must comply with the Canadian Constitution and federal and provincial/territorial privacy legislation to obtain consent for disclosing information about participants [4]. Researchers must also ensure that they have the necessary permissions and approvals to share data [4].
>
> Ultimately, the decision to share human subject data must be made with caution and careful consideration of the potential risks and consequences [5]. Researchers must weigh the benefits of sharing data against the potential harm it may cause to participants and ensure that they are taking steps to protect participants' privacy and confidentiality [5].
>
> [Response_End]

<details><summary>Source [0]: Ethical aspects of data sharing and research participant protections. (https://doi.org/10.1037/amp0000240)</summary>

# Ethical aspects of data sharing and research participant protections. ## Abstract Open access is fast becoming the norm across science. Sharing research data broadly has the potential to accelerate scientific progress, optimize the value of data, and promote scientific integrity. However, data sharing also poses new practical and ethical challenges to the conduct of research with human participants. This article provides an overview of how open access to research data has impacted the core principles of research ethics-respect for persons, beneficence, and justice-and, in turn, how a reinterpretation of these principles translates to procedures for the protection of the rights and wellbeing of human research participants. ## Ethical Framework The ethical underpinnings of human research participant protections in the United States are firmly grounded in occidental philosophical traditions that hold individual rights as paramount. Thus, the authors of the seminal document The Belmont Report (National Commission for the Protection of Human Subjects of Biomedical & Behavioral Research, 1978), which provides the ethical framework for research with human participants, delineated three basic principles: (a) respect for persons, (b) beneficence, and (c) justice. Respect for persons requires recognizing individuals as autonomous agents with unalienable rights for selfdetermination. This principle extends further to provide additional protection to those less capable of self-determination, whether from decreased mental capacity, illness, or circumstances of vulnerability (e.g., prison inmates). Abiding by this principle in the research setting requires researchers to present prospective participants with the opportunity to provide voluntary informed consent.

</details>

<details><summary>Source [1]: Qualitative Data Sharing: Data Repositories and Academic Libraries as Key Partners in Addressing Challenges (https://doi.org/10.1177/0002764218784991)</summary>

While most big data are used to conduct quantitative analysis, big data from social media such as social networking sites and blogs can be used for qualitative analysis, and sharing these data sources for secondary use present an as-yet-unsolved ethical challenge for qualitative researchers. Items posted on social media and blogs are unique types of qualitative data that do not neatly fit into the traditional definition of human subject data. Such data, often mined from the web without explicit consent from research subjects, have additional considerations that are not addressed by traditional ethical frameworks such as the Common Rule, and may not be subject to IRB oversight (Metcalf & Crawford, 2016;Shilton & Sayles, 2016). The ethical considerations for social media data generally relate to sensitivity of topics, vulnerability of populations, informed consent, expectation of privacy, and social media platform terms of service (Mannheimer & Hull, 2017). While posts to social networking sites and blogs can be analyzed using conventional social science research methods like ethnographic observation and close reading, they can also be mined and analyzed on a large scale using computational methods (Bruns, 2013). When conducting such largescale analysis, obtaining informed consent from each social media user becomes impractical, if not impossible. Additionally, while social media content is often posted publicly to the web, social media users may not intend for their posts to be seen beyond their immediate community (Marwick & boyd, 2014), and they are likely not aware that their posts can be collected and used for research purposes.

</details>

<details><summary>Source [2]: The Qualitative Transparency Deliberations: Insights and Implications (https://doi.org/10.1017/s1537592720001164)</summary>

The other main area of disagreement, even among research communities that embrace the overall value of research transparency, is the advisability of data sharing. Importantly, there was universal agreement that the sharing of qualitative data should not be uniformly required, given the considerable costs and risks of data sharing for some forms of research. 90 Nonetheless, qualitative research communities vary widely in the degree to which they view data sharing as the presumptively appropriate practice. At one end of the spectrum, working groups III.4 and III.5 recommend that scholars using QCA and content analysis, respectively, make the qualitative source material used for such analyses accessible wherever ethical considerations, confidentiality agreements, and legal and copyright restrictions do not prohibit doing so. The groups on text-based sources and on comparative methods and process-tracing similarly argue in favor of sharing raw data to the extent that doing so is consistent with ethical obligations and feasible at reasonable cost. The text-based sources group further argues that, in most cases, it should not be too onerous for scholars to provide extended source excerpts to back up key claims, especially if scholars plan to do so from the outset of a research project. By contrast, groups focused on human-subjects research and higher-risk contexts (I.2, II.2, IV.2, and IV.3), while recognizing intellectual value in sharing some evidentiary materials, argue against any default practice of data sharing and in favor of great caution in considering the implications of this strategy for human participants and their communities.

</details>

<details><summary>Source [3]: Qualitative Data Sharing: Data Repositories and Academic Libraries as Key Partners in Addressing Challenges (https://doi.org/10.1177/0002764218784991)</summary>

Second, textual and visual qualitative data are often constrained by copyright, raising concerns about how qualitative data can be shared while respecting proprietary rights. Third, there is a risk of decontextualizing a study through the data sharing process. While data repositories and academic libraries do not provide simple solutions to these challenges, they can partner with researchers and connect them with other relevant specialists to examine these continuing challenges and discuss potential solutions. ## Continuing Challenge 1: Qualitative Data From Big Data Sources An additional challenge surrounding qualitative data reuse is the availability of "big data." While most big data are used to conduct quantitative analysis, big data from social media such as social networking sites and blogs can be used for qualitative analysis, and sharing these data sources for secondary use present an as-yet-unsolved ethical challenge for qualitative researchers. Items posted on social media and blogs are unique types of qualitative data that do not neatly fit into the traditional definition of human subject data. Such data, often mined from the web without explicit consent from research subjects, have additional considerations that are not addressed by traditional ethical frameworks such as the Common Rule, and may not be subject to IRB oversight (Metcalf & Crawford, 2016;Shilton & Sayles, 2016). The ethical considerations for social media data generally relate to sensitivity of topics, vulnerability of populations, informed consent, expectation of privacy, and social media platform terms of service (Mannheimer & Hull, 2017).

</details>

<details><summary>Source [4]: Preserving privacy in the era of openness: Commentary on open science requirements for identifiable data in psychological science journals (https://doi.org/10.1037/amp0001282)</summary>

Keywords: open data, informed consent, videos, identifiable data, privacy There is a growing tension and fundamental conflict in psychological science where open science (OS) and the ethical (and sometimes legal) protections of identifiable human subject data are at odds. While the replication crisis has emphasized researchers' responsibility to science through facilitating the open sharing of data and materials, researchers also have a primary obligation to maintain participant confidentiality, especially of identifiable data such as video, audio, or photograph (American Psychological Association, 2017, Section 4.01). These tensions most notably collide during the publication process—yet there appears to be much diversity across journals regarding how identifiable data, which are often the most valuable data (Dennis et al., 2019), are (and should be) handled. This article was published Online First December 7, 2023. Mollie A. Ruben https://orcid.org/0000-0001-8918-8932 The authors thank Judith A. Hall and Frank J. Bernieri for giving comments on an earlier version of the article and instilling in both authors a deep commitment to ethics and the protection of human subjects. There are no data, analysis codes, or research materials associated with the current commentary. Mollie A. Ruben played coleading role in conceptualization, writing– original draft, and writing–review and editing and a lead role in supervision. Morgan D. Stosic played coleading role in conceptualization, writing– original draft, and writing–review and editing.

</details>

<details><summary>Source [5]: Open Data in Qualitative Research (https://doi.org/10.1177/1609406918823863)</summary>

## Ethical and Legal Issues The debate on open data is further polarized when ethical and legal implications surrounding potential harm to participants are considered. Specifically, ethical and legal concerns relating to informed consent as well as protection of privacy and confidentiality support the position that some qualitative data should not be open for sharing and reuse. First, informed consent is positioned within the principles of beneficence and nonmaleficence, which are protected by laws and professional associations that help govern professional behavior (Canadian Nurses Association, 2008). Canadians' rights to privacy are protected under the Canadian Constitution and federal and provincial/territorial privacy legislation. Researchers are required to comply with these legal requirements to obtain consent for disclosing information about the participants (Government of Canada, 2016a). Furthermore, institutional research ethics boards (REB) are in place to assure that appropriate steps are taken to protect the rights to privacy and confidentiality of participants in a research study. It is also a professional responsibility of researchers who are guided by the research councils' policies to practice ethically (Government of Canada, 2016b). Ultimately, however, it is the researcher who is responsible for protecting the participants (Government of Canada, 2016b). Consequently, there are legal and ethical concerns as to whether the sharing and reuse of data can be done while complying with legislation, the REB, and professional associations. Heaton (2008) addresses the difficulties involved in obtaining informed consent from participants for sharing their narrative data with others and then reusing it for purposes other than those for which it was originally intended for and collected.

</details>


## pr01

**Question:** What is preregistration and why is it important?

**Category:** open science &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 1.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> Preregistration is the process of specifying and documenting the key aspects of an empirical study prior to conducting the study, and submitting these details to a registry prior to actually conducting the work [0]. This involves outlining the research questions, hypotheses, method, and analysis plan prior to data collection and analysis [3]. Preregistration is important for several reasons. Firstly, it helps ensure more systematic planning and coordination, such that all 'bases' of a study are more likely to be covered before the work begins [0]. Secondly, preregistration helps ensure that everyone on a research team has a mutual understanding of the work to be conducted, such that any misunderstandings or knowledge gaps can be resolved early on in the research process [0]. Thirdly, laying out all of the major components of a study beforehand can improve researchers' appreciation of the scope and timeline of the work [0].
>
> Preregistration also promotes transparency and credibility in research [6]. By publicly posting plans on central components of the research process, researchers can differentiate between exploratory and confirmatory research, which may evoke different levels of confidence [6]. Additionally, preregistration can minimize questionable research practices like HARKing and publication bias [6]. Preregistration initiatives like Registered Reports, where preregistered plans are peer-reviewed before data collection and receive in-principle acceptance, are of great value to basic research [6].
>
> Preregistration is also essential in single-case design research, where researcher bias and postdictive methods can play a significant role in the identification of evidence-based practices [2]. Preregistration can lend greater transparency and validity to single-case methodology, making it easier to distinguish between confirmatory and exploratory research [2].
>
> In summary, preregistration is a crucial step in the research process that promotes systematic planning, transparency, and credibility. By preregistering their plans, researchers can ensure that their study is well-planned, and their results are reliable and trustworthy [0].
>
> [Response_End]

<details><summary>Source [0]: Preregistration for Quantitative Research in Psychology Template (https://doi.org/10.1037/0000409-043)</summary>

By supporting this work, the APA, BPS and DGPs also want to provide guidance and highlight the importance of preregistration for psychological science. Preregistration of studies means the specification and documentation of the key aspects of an empirical study prior to conducting the study, and submitting these details to a registry prior to actually conducting the work. Most noteworthy, the preregistration should include the hypotheses, study design, data acquisition and data analysis plans. Submitting a preregistered plan has several benefits. First, it helps ensure more systematic planning and coordination, such that all 'bases' of a study are more likely to be covered before the work begins. Second, preregistration helps ensure that everyone on a research team has a mutual understanding of the work to be conducted, such that any misunderstandings or knowledge gaps can be resolved early on in the research process. Third, laying out all of the major components of a study beforehand can improve researchers' appreciation of the scope and timeline of the work. Through preregistration, additional benefits are hoped to accrue as the work is conducted and written up for publication. For example, by preregistering their work, researchers specify the nature of their confirmatory hypotheses, such that the distinction from other exploratory hypothesis-generating work is made very clear. Presenting results from exploratory work is clearly important and vital to science. But presenting exploratory results as if they were confirmatory misrepresents the scientific process (Munafò et al., 2017), and preregistration can serve as a strong reminder to avoid this serious problem.

</details>

<details><summary>Source [2]: Preregistration in Single-Case Design Research (https://doi.org/10.1177/0014402919868529)</summary>

We extend this argument by suggesting that preregistration of these descriptions matters as well, and we provide specific recommendations on what information to preregister, why it is important to do so, and what preregistration of that information might look like in single-case design research. As single-case research contributes to the identification of evidence-based practices in special education and related fields, the role that researcher bias and postdictive methods can play in single-case designs must be grappled with. If not, then conclusions about what works for children and youth with and at risk for disabilities based on single-case design are at risk of being misguided and invalid. Preregistration is one method that may lend greater transparency and validity to single-case methodology. Like design and reporting standards, however, professional monitoring and recognition on the part of journals, editors, reviewers, and research consumers are necessary to drive such improvements forward. Such recognition will be particularly important to incentivize the use of preregistration, given that initial preregistration and the potential for ongoing updates to that preregistration will add to the workloads of single-case researchers. During the conduct of a single-case study, decisions to implement an IV might be made less than 24 hours before the implementation actually takes place. Asking a researcher to prepare for that implementation, call research assistants, make sure that all materials are prepared, and update a preregistration at the same time will be taxing. Although the potential benefits of preregistration are substantial, we suspect that not all researchers will agree that these gains are worth the extra effort. Nonetheless, to borrow language from Nosek et al.

</details>

<details><summary>Source [3]: Easing Into Open Science: A Guide for Graduate Students and Their Advisors (https://doi.org/10.1525/collabra.18684)</summary>

Preregistration (Level: Medium) Preregistration (Level: Medium) What? What? The use, function, and benefit of preregistration for psychological research is debated, and we encourage readers interested in those debates to consult these different views (Lakens, 2019;Nosek et al., 2019;Szollosi et al., 2020). Putting those debates aside, in the most basic form preregistration refers to posting a timestamped outline of the research questions, hypotheses, method, and analysis plan for a specific project prior to data collection and/or analysis (see Nosek et al., 2018). We rate preregistration as medium because although researchers should have all the information necessary for a preregistration before beginning their research, they might be used to making a bit of this up as they go along (so this brings the effort to the front end of the project). However, as we discuss below, preregistrations can vary in difficulty from easy (just hypotheses and brief methods) to difficult (preregistering in detail including writing analysis code beforehand). Why? Why? The primary purpose of preregistration is to more clearly distinguish between the decisions and hypotheses made before the study began ("confirmatory" research) and decisions made after seeing the data or in the absence of specific hypotheses ("exploratory" research; see Wagenmakers et al., 2012). By outlining the research questions, hypotheses, method, and analysis plan prior to data collection and analysis, your intentions and predictions are clear and time stamped.

</details>

<details><summary>Source [6]: Pre-registration: Weighing costs and benefits for researchers (https://doi.org/10.1016/j.obhdp.2021.05.006)</summary>

#### **Opportunities for preregistration** Preregistration is the practice of publicly (typically immediately but occasionally following an embargo period) publishing plans on central components of the research process (e.g., hypotheses, methods, and analyses) before data collection begins. Preregistration is typically endorsed based upon claims for a range of benefits for transparency and credibility (Rubin 2020), including differentiating between exploratory and confirmatory research which may evoke different levels of confidence, minimizing questionable research practices like HARKing, and publication bias (Nosek et al. 2019). Preregistration initiatives like Registered Reports (Chambers 2013), where preregistered plans are peer-reviewed before data collection and receive in-principle acceptance where subsequent publication is virtually guaranteed regardless of the eventual results, are of great value to basic research (Scheel, Schijen, and Lakens 2021; Soderberg et al. 2021). Indeed, developments in preregistration have been well adopted by researchers in medicine and neuro, cognitive, and social psychological fields, but less so in applied areas, such as occupational, forensic, and educational psychology (e.g., Van't Veer and Giner-Sorolla 2016), with clinical trials as a unique exception. Furthermore, there is a deficit for applications which are not intended for this traditional academic publishing model.

</details>


## oa01

**Question:** What is open access and what are advantages and disadvantages?

**Category:** open science &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 1.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> Open access refers to the removal of major obstacles to accessing, sharing, and reusing the outputs of scholarly research [0]. The main benefits of open access include promoting openness and the dissemination of knowledge, allowing researchers who cannot afford to purchase articles to have access, and facilitating reproducibility and replicability of research [1]. Open access can also help ensure stakeholders can view the full range of research, including results that disagree with expectations held by researchers or others, and mitigate against fraud by opening published information to scrutiny [2].
>
> However, open access has several limitations. For example, it cannot solve methodological or ethical problems in completed research or publications, and it can only make these issues visible and possible to scrutinize [2]. Moreover, open access cannot solve poor or incomplete reporting, and fully accessible papers can still lack the minimum information considered necessary to judge the validity of the work [2]. Additionally, open access has been criticized for favoring large groups with a lot of money, regardless of whether their ideas are innovative or will have an impact on society [6].
>
> Despite these limitations, open access has several advantages. For instance, it can provide a broad citation advantage for researchers who publish openly, as well as additional benefits to the non-academic dissemination of their work [5]. Open access can also save both publishers and research funders considerable amounts of financial resources, and provide some economic benefits to traditionally subscription-based journals [5]. Furthermore, open access has the potential to advance citizen science initiatives and level the playing field for researchers in developing countries [5].
>
> In terms of routes for open access, authors can choose between several options, including open access journals, hybrid journals, and repositories [3]. However, authors should be aware of the potential drawbacks of open access, such as the risk of predatory publishers and the need to carefully evaluate the quality of open access journals [3].
>
> Overall, open access has the potential to remove barriers to reading and using research, but it is not a panacea for all the problems in the research process. It is a necessary component of open and reproducible science, but alone it is not enough to ensure research quality [4].
>
> [Response_End]

<details><summary>Source [0]: Open access journal publication in health and medical research and open science: Benefits, challenges and limitations (https://doi.org/10.1136/bmjebm-2022-112126)</summary>

Open access has the potential to solve the problem of accessibility. It benefits the final users of the evidence produced, who are patients and healthcare professionals in the case of evidencebased medicine. It also benefits researchers, who can avoid waste from reproducing investigations unnecessarily or having to reinvent procedures that are not clearly explained. To help authors to decide whether to choose open access and how, we summarise the main benefits of open access, the routes for open access and their challenges. # Benefits of open access publication of health research ## The right to access research As previously mentioned, the problem of inaccessible research disproportionately affects certain groups and countries. Knowledge produced by health research can be thought of as a public $good.<sup>7 8</sup>$ Much biomedical research is funded by public money, such as taxes or charitable donations. Yet members of the public are often unable to access the results of research without paying access fees. The main beneficiary of open access publication is the reader who can freely access, read, use and benefit from research.<sup>9</sup> Eliminating paywalls is the first step towards more equitable knowledge-sharing However, who is responsible for ensuring publication occurs without a paywall is something currently under debate.<sup>8</sup> # Reproducibility Open access publications can facilitate reproducibility and replicability of research.

</details>

<details><summary>Source [1]: Responsible Conduct of Research (no link)</summary>

The chief advantages of an open-access system are that it promotes openness and the dissemination of knowledge, and it allows researchers who cannot afford to purchase articles, such as researchers from developing countries, to have access. In 2005, the NIH adopted an open-access policy (Schroter et al. 2005). The NIH now requires that all of the articles that are funded by NIH are available to the public for free on its website. The rationale for this policy is that since the public has already funded the research, it should not have to pay a second time for access. Publishers have objected that this policy will put them out of business by undercutting the fees they charge to access NIH-funded articles (Kaiser 2004). It remains to be seen whether the traditional publishing model can survive in the electronic age. > public ation a nd peeR R ev iew **[ 161 ]** 9780199376025 ~~-~~ Shamoo.indb 161 8/5/14 7:20 PM <mark>OUP-FIRST UNCORRECTED PROOF, August 6, 2014</mark>

</details>

<details><summary>Source [2]: Open access journal publication in health and medical research and open science: Benefits, challenges and limitations (https://doi.org/10.1136/bmjebm-2022-112126)</summary>

small businesses that might not have access to journal subscriptions[.9 13 14](#page-4-6) ## **Influence on policy** Open access helps ensure stakeholders can view the full range of research, including results that disagree with expectations held by researchers or others. As a result, patients, advocacy groups, policymakers and politicians can make better-informed decisions and future public resources are less likely to be wasted on interventions that do not work.[9 13](#page-4-6) Widespread open access can also help mitigate against fraud by opening published information to scrutiny[.13](#page-4-11) ## **Limitations of open access** Open access cannot solve methodological or ethical problems in completed research or publications. It can only make these issues visible and possible to scrutinise, allowing cases of misconduct and fraud to be more easily and openly identified and discussed. Being accessible is not a synonym of good science, even if it is open science. Open access does not solve poor or incomplete reporting. Fully accessible papers can still lack the minimum information considered necessary to judge the validity of the work. ## **Routes for open access: benefits and challenges** Authors can choose between several open access routes that have developed within and outside the existing publishing system. Author choice might be dictated by personal choice, funder requirements, institution requirements, national mandates, and journal options. #### **Open access outside scholarly publishing** Authors can make their work available to all separately from a peer-reviewed publication.

</details>

<details><summary>Source [3]: Open access journal publication in health and medical research and open science: Benefits, challenges and limitations (https://doi.org/10.1136/bmjebm-2022-112126)</summary>

(#page-4-10) Although similar to hybrid from readers' perspective, bronze open access provides fewer benefits to readers because these free-to-read articles remain under restrictive copyright, so cannot be shared or reused.(#page-4-10) Library/institutional subscriptions are not affected. Authors are unable to choose between the free-to-read or pay-to-read option. As there is no agreement with the authors, journals can move these articles back to pay-to-read at any time. ## **Predatory publishers** Unscrupulous organisations have capitalised on the open access movement. They masquerade as scholarly publishers, soliciting APCs from authors. However, they do not adhere to any of the quality markers of scholarly publishing, such as robust peer review, indexing or archiving. A distinction should be drawn between these so-called predatory publishers, which have no interest in improving their processes or contributing to the evidence base, and publishers of low-quality journals or those that are starting out[.30 31](#page-5-10) Authors can avoid predatory journals by using the Think Check Submit(#page-5-11) checklist. ## **Conclusion** Open access has the potential to remove barriers to reading and using research. It is a necessary component of open and reproducible science, alongside sharing data, code and materials, but alone it is not enough to ensure research quality. Current models for open access have different benefits and burdens for authors, readers, funders, publishers and others, with no model meeting all needs.

</details>

<details><summary>Source [4]: A reputation economy: how individual reward considerations trump systemic arguments for open access to data (https://doi.org/10.1057/palcomms.2017.51)</summary>

Furthermore, we control for sex and age. For those independent variables, which concern opinions, we assessed approval or rejection of a statement by grouping the responses into two categories. ### Results To make the results of our study more accessible we structured them by reference to the five research questions we introducted earlier. What is the researchers' general opinion on open access to **data?** Despite the fact that open access to research data is widely considered a way of fostering scientific progress and although it is promoted by science policy makers, few researchers make their data publicly available. To see how researchers view open access to data, one question battery targeted the researchers' general opinion. Table 2 summarizes the results to this set of questions. The results show a general consensus in the research community that open access to data benefits academic research and that researchers should make their data publicly available. Eighty-three per cent of the respondents agree that openly available research data is a major contribution to scientific progress. Seventy-six per cent of the respondents say that other researchers should make their data publicly available. The majority of the researchers in our survey sees no disadvantage in making data publicly available. Seventy-four per cent disagree that they are deterred from publishing articles if a journal requires the publication of data. Seventeen per cent of the researchers agree with the statement that sharing data brings more disadvantages than advantages. While the results may be influenced by social desirability, the clarity of the responses shows that open access to research data is considered beneficial for research in general and is not considered detrimental to the individual researcher who shares data.

</details>

<details><summary>Source [5]: The academic, economic and societal impacts of Open Access: an evidence-based review (https://doi.org/10.12688/f1000research.8460.1)</summary>

This review aims to be a resource for current knowledge on the impacts of Open Access by synthesizing important research in three major areas: academic, economic and societal. While there is clearly much scope for additional research, several key trends are identified, including a broad citation advantage for researchers who publish openly, as well as additional benefits to the non-academic dissemination of their work. The economic impact of Open Access is less well-understood, although it is clear that access to the research literature is key for innovative enterprises, and a range of governmental and non-governmental services. Furthermore, Open Access has the potential to save both publishers and research funders considerable amounts of financial resources, and can provide some economic benefits to traditionally subscription-based journals. The societal impact of Open Access is strong, in particular for advancing citizen science initiatives, and leveling the playing field for researchers in developing countries. Open Access supersedes all potential alternative modes of access to the scholarly literature through 1 2 3 4 5 version 3 (revision) ## Introduction Open Access (OA) refers to the removal of major obstacles to accessing, sharing and re-using the outputs of scholarly research. The rationale is that the research process is facilitated by ensuring rapid and widespread access to research findings such that all communities have the opportunity to build upon them and participate in scholarly conversations. As such, the major drivers behind OA relate to within-and between-community equality (Veletsianos & Kimmons, 2012), as well as bridging the global North-South research divide (Adcock & Fottrell, 2008).

</details>

<details><summary>Source [6]: Habits and perceptions regarding open science by researchers from Spanish institutions (https://doi.org/10.1371/journal.pone.0288313)</summary>

When comparing the scores for the reasons and hindrances to open publication, there are few effects dependent on discipline, age or gender of those surveyed (*η*2 = 0.002– 0.024). One of the very aspects highlighted by participants in the questionnaire is that of the funding problems that may arise when publishing in a commercial open access journal, because this favours inequality between teams with projects with funding and emerging research groups, as revealed in the survey comments. "Open publication only benefits the large groups who can easily access the knowledge of smaller ones and compete in unequal conditions. So, open publication, far from democratizing (I share my knowledge with colleagues I value, respect and trust), it increases inequality by excessively favouring large groups with a much greater capacity for competing since public funding always favours larger groups because they appear to have a safer value and be more profitable" [R\_46]. "Open access is detrimental to emerging groups or countries with few economic opportunities in terms of disseminating innovative research. Open access only favours researchers with a lot of money, regardless of whether their ideas are innovative or will have an impact on society" [R\_77]. <span id="page-7-0"></span>On the other hand, when researchers are asked about their preferred means of disseminating their research work with open access, the preferred venue was in an open-access journal (*N* = 303,47%), ahead of hybrid journals (*N* = 171, 26%) or storage in a repository (green way, *N* = 142, 22%).

</details>


## new17

**Question:** What is p-hacking?

**Category:** open science &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 1.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> P-hacking refers to the intentional or unintentional misuse of statistical techniques, through the exploitation of researcher degrees of freedom, that may lead to artificially significant results for a predetermined hypothesis of interest [0]. This practice involves reanalyzing data in many different ways to yield a target result [2], or collecting or selecting data or statistical analyses until nonsignificant results become significant [3]. P-hacking can lead to the detection of false-positive findings, but it may also lead to the detection of true-positive findings [2]. The practice is considered one of the many questionable research practices (QRPs) linked to the replication crises in fields like psychology and medicine [5].
>
> P-hacking can take many forms, including:
>
> *   Performing multiple measurements in an experiment
> *   Arbitrarily trimming data
> *   Performing many post-hoc analyses of data
> *   Selectively reporting only statistically significant results [3]
>
> The consequences of p-hacking are not always negative. In some cases, p-hacking may be warranted, particularly when it involves the use of statistical techniques that may lead to distorted experimental results [5]. However, the practice is often criticized on epistemic grounds, and its regular practice can lead to harmful policies and recommendations [5].
>
> Preregistration and transparency can help identify p-hacking [6]. Researchers can confirm the absence of p-hacking in their research reports by actively affirming the disclosure of their data collection stopping rule, data exclusions, measures, and manipulations [6].
>
> [Response_End]

<details><summary>Source [0]: p-Hacking: Its Costs and When It Is Warranted (https://doi.org/10.1007/s10670-024-00834-3)</summary>

We are now well-positioned to provide a definition: p-hacking is the intentional or unintentional misuse of statistical techniques, through the exploitation of researcher degrees of freedom, that may lead to artificially significant results for a predetermined hypothesis of interest. This definition helps to more reliably identify cases of p-hacking and differentiate between its practice, and other analytic offenses. Moreover, it captures several aspects of p-hacking that others have highlighted, while encompassing the range of strategies that constitute the practice. ## 2.2 Transparency Before addressing the prevalent position on p-hacking, it's worth addressing a potential objection to my definition. One might argue that p-hacking is not just a question of statistical practices, but also of scientific integrity. According to this objection, while intention is not central to the practices that amount to p-hacking, it is central to how we report our findings. Put another way, what's important when it comes to p-hacking is whether one is transparent about their analytic procedures. Indeed, the norms of the Open Science movement call for full disclosure of one's methods and results. Such transparency is instrumental for mitigating the replication crises facing medicine and psychology and can help us calibrate our confidence in results where QRPs have occurred (Ioannidis, 2008). So, according to this objection, the consequences of p-hacking are different if we take transparency into consideration. Therefore, it may be argued that another necessary feature of p-hacking is that it involves some opaque, selective, or inaccurate reporting of analytic procedures or results.

</details>

<details><summary>Source [2]: The Problem of New Evidence: P-Hacking and Pre-Analysis Plans (https://doi.org/10.33392/diam.1587)</summary>

Thomas Insel, a former director of the National Institute for Mental Health, summarizes the defi nition in Simmons et al. (2011) in slightly different terms: p-hacking, he holds, "refers to the practice of reanalyzing data in many different ways to yield a target result." Meanwhile, biologists Head et al. (2015) write, "'p-hacking' occurs when researchers collect or select data or statistical analyses until nonsignifi cant results become signifi cant" and when, the authors continue, "researchers try out several statistical analyses and/or data eligibility specifi cations and then selectively report those that produce signifi cant results." These claims illustrate the variety of notions of 'p-hacking' fl oating around in contemporary discourse. Further complicating matters, the term 'p-hacking' is often used interchangeably with other terms including 'data-dredging,' 'data-mining' and 'specifi cation searching.' To summarize, the term encompasses practices including: performing multiple measurements in an experiment, arbitrarily trimming data, performing many post-hoc analyses of data, and selectively reporting only statistically signifi cant results. Many scientists claim that methods described as p-hacking are epistemically nefarious, because these practices are liable to lead to the detection of false-positive fi ndings. However, these practices may also lead to the detection of true-positive fi ndings. Some scientifi c disciplines *require* the use of methods that are, broadly construed, constitutive of p-hacking, such as astronomy and genetics.

</details>

<details><summary>Source [3]: The Problem of New Evidence: P-Hacking and Pre-Analysis Plans (https://doi.org/10.33392/diam.1587)</summary>

P-hacking and the related issue of publication bias are frequently cited as twin evils at the core of the ongoing 'replication crisis' in the social and medical sciences, and are the targets of proposals for policy reforms intended to rework the incentive structures of scientifi c publishing. What exactly is p-hacking? To illustrate the range of methods described as p-hacking, consider the following recent claims about p-hacking from researchers in a variety of disciplines. An infl uential defi nition from psychologists Simmons et al. (2011) is that p-hacking amounts to "fl exibility in (a) choosing among dependent variables, (b) choosing sample size, (c) using covariates, and (d) reporting subsets of experimental conditions." Thomas Insel, a former director of the National Institute for Mental Health, summarizes the defi nition in Simmons et al. (2011) in slightly different terms: p-hacking, he holds, "refers to the practice of reanalyzing data in many different ways to yield a target result." Meanwhile, biologists Head et al. (2015) write, "'p-hacking' occurs when researchers collect or select data or statistical analyses until nonsignifi cant results become signifi cant" and when, the authors continue, "researchers try out several statistical analyses and/or data eligibility specifi cations and then selectively report those that produce signifi cant results." These claims illustrate the variety of notions of 'p-hacking' fl oating around in contemporary discourse.

</details>

<details><summary>Source [5]: p-Hacking: Its Costs and When It Is Warranted (https://doi.org/10.1007/s10670-024-00834-3)</summary>

I appeal to non-epistemic judgments to defend the view that there are situations in which p-hacking may be warranted. ## 1 Introduction P-hacking involves the use of statistical techniques that may lead to distorted experimental results. It is often criticized on epistemic grounds. Many argue that since p-hacking raises the probability of acquiring false-positive results, there's little warrant in believing the conclusions of studies where it occurred (Simmons et al., 2011;Simonsohn et al., 2014). Indeed, the practice is considered one of the many questionable research practices (QRPs) linked to the replication crises in fields like psychology and medicine (Munafò et al., 2017;Open Science Collaboration 2015). Where these arguments emphasize the epistemic side of the case against p-hacking, others mention the practical aspect. It's suggested that because p-hacking increases the rate of false findings in published results, its regular practice, particularly in socially impactful fields like economics and medicine, can lead to harmful policies and recommendations (Head et al., 2015). More broadly, some have argued that pervasive p-hacking contributes to a general distrust of science (Colquhoun, 2017). Arguments against p-hacking are commonplace, yet few unpack the full extent of the practice's potential consequences. Rather, these arguments overemphasize the negative effects of p-hacking, disregarding any sentiment that the practice may, in limited cases, be useful or warranted.

</details>

<details><summary>Source [6]: Does preregistration improve the credibility of research findings? (https://doi.org/10.20982/tqmp.16.4.p376)</summary>

**Identifying** p**-hacking.** p-hacking refers to resultcontingent tests in which researchers continue to conduct analyses until they achieve a significant result (e.g., Simmons, Nelson, & Simonsohn, [2011\)](#page-11-15) . Preregistration's historical transparency may be used to identify p-hacking. However, historical transparency is not necessary when contemporary transparency is available. For example, researchers can confirm the absence of p-hacking in their research reports by (a) actively affirming the disclosure of their data collection stopping rule, data exclusions, measures, and manipulations (Simmons, Nelson, & Simonsohn, [2012\)](#page-11-16), (b) providing logical and principled justifications for nonstandard data exclusions and analytical approaches (Giner-Sorolla, [2012,](#page-10-15) p. 568), (c) providing public access to their standard data analysis procedures (e.g., Lin & Green, [2016\)](#page-10-16), (d) providing public access to their research materi- als, data, and coding information (e.g., Aalbersberg et al., [2018\)](#page-9-9), and (e) reporting the results of robustness analyses (e.g., Thabane et al., [2013\)](#page-11-9). **Identifying Optional Stopping.

</details>


## gl24

**Question:** What is a Registered Report and how does it change the peer review process in scientific publishing?

**Category:** open science &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the papers

**Judge:** 1.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> [Response_Start]
> A Registered Report is a type of empirical publication that involves peer review of a study proposal before data collection [0]. This process is designed to prevent publication bias and minimize the incentive for authors to engage in questionable research practices [2]. The Registered Reports process involves two stages of peer review: Stage 1, where the study proposal is reviewed and accepted in principle, and Stage 2, where the final manuscript is reviewed and published [3].
>
> The Registered Reports process changes the peer review process in several ways. First, it focuses the power of peer review on the quality and rigor of experimental design, rather than assessing which manuscripts to publish based on whether results are deemed novel or groundbreaking [2]. Second, it requires authors to adhere to a pre-approved methodology and analysis pipeline, which prevents a host of questionable practices that promote false discoveries [4]. Finally, it ensures that the editorial decision is based on the significance of the research question and validity of the methods, rather than on whether results are novel or statistically significant [4].
>
> The Registered Reports process has several attractive characteristics. It is immune to publication bias, as the decision to accept or reject manuscripts is based on the significance of the research question and validity of the methods, never on whether results are novel or statistically significant [4]. It also requires authors to adhere to a pre-approved methodology and analysis pipeline, which prevents a host of questionable practices that promote false discoveries [4]. Additionally, it incentivizes rigorous methodology and reduces questionable research practices, as researchers cannot manipulate their analyses to obtain significant results [5].
>
> The Registered Reports process has been adopted by many journals across various fields, including psychology, neuroscience, and medicine [5]. In 2019, there were approximately 156 journals offering Registered Reports, and this number has jumped to 319 at the time of writing this manuscript, an increase of 104% [5]. Of those 319, only 14 are journals related to language or linguistics [5].
>
> In summary, a Registered Report is a type of empirical publication that involves peer review of a study proposal before data collection. It changes the peer review process by focusing on the quality and rigor of experimental design, requiring authors to adhere to a pre-approved methodology and analysis pipeline, and ensuring that the editorial decision is based on the significance of the research question and validity of the methods.
>
> [Response_End]

<details><summary>Source [0]: Process and Bureaucracy: Scienti ﬁ c Reform as Civilisation (https://doi.org/10.1177/02704676221126388)</summary>

3 The same expectation of how the sequential process of science should look like, generated a second bureaucratic innovation: registered reports. Where preregistration is an additional step in the research process, following the design phase but preceding experimentation, analysis and publication, registered reports draws a small part of the publication and review process forward. Registered reports are part of the same reform agenda as preregistration, but they seek to solve a different problem. Registered reports primarily target the problem of publication bias and focuses not on the execution of studies, but on their display in the scientific literature. It draws from the realisation that positive results are overrepresented in published work, and negative or null results are underrepresented. In 2013, the journal Cortex came up with a new scientific genre, called the registered report, to "provide authors with a publishing option that neutralises bad incentives, permitting the publication of null results and encouraging replication attempts" (Chambers, 2013). It rearranges the publication process: "The Registered Report format splits conventional peer review in half" (Chambers, 2019) in which the editors and reviewers first receive a so-called "Stage 1" manuscript that "includes an overview of the background literature, preliminary work, theory, hypotheses and proposed methods, including the study procedures and analysis plan" (Chambers, 2019) which they may review and ultimately accept for publication before the study is actually conducted.

</details>

<details><summary>Source [2]: Registered Reports : Realigning incentives in scientiﬁc publishing ScienceDirect (no link)</summary>

These practices have proliferated within an incentive structure that places the immediate career needs of individual scientists in opposition to the longer-term objectives of science (Nosek, Spies, & Motyl, 2012). In 2013, Cortex launched the Registered Reports initiative in an effort to realign these incentives (Chambers, 2013). In contrast to conventional publications, Registered Reports focus the power of peer review on the quality and rigour of experimental design, rather than assessing which manuscripts to publish based on whether results are deemed novel or groundbreaking. Registered Reports are thoroughly reviewed and revised before researchers collect data. Study proposals that are judged to be methodologically valid, detailed, replicable, and which address an important scientific question are then offered in-principle acceptance, in which the journal agrees to publish the results regardless of whether they confirm or disconfirm the experimental hypothesis. This mechanism prevents publication bias while also minimising, as much as possible, potential influences of selective reporting, post hoc hypothesising, and low statistical power. Most importantly, by making the outcomes of hypothesis tests irrelevant in reaching editorial decisions, Registered Reports minimise the incentive for authors to engage in questionable research practices in the first place. At this stage, readers may be interested to know some practical details of the Registered Reports review process. The Cortex editorial sub-team generally triages submissions with 1 week, deciding either to reject manuscripts outright, to invite a revision to meet the necessary standards for further consideration, or to send the manuscript immediately for Stage 1 in-depth review.

</details>

<details><summary>Source [3]: Evaluating Registered Reports: A Naturalistic Comparative Study of Article Impact (https://doi.org/10.31219/osf.io/5y8w7)</summary>

A solution is to integrate preregistration with publishing incentives with a model called Registered Reports (Chambers, 2013; Nosek & Lakens, 2014). The Registered Report (RR) publishing model is comprised of two key features: (1) peer review by the journal in advance of observing the research outcomes, and (2) if successful in that initial peer review, pre-commitment to publishing the results as long as all outcome-irrelevant quality control criteria are met. That is, preregistration is built into the RR publication process with expert peer review and editors giving in-principle acceptance to a preregistered protocol for publication. Then in the final report, authors clearly distinguish between confirmatory analyses specified in the accepted protocol and exploratory analyses that were conducted afterwards. Also, RRs address publication bias by committing to publish the results regardless of outcome eliminating privileging of positive results. Papers can be rejected in the second stage of peer review because of failures to follow through with the specified protocol, or evidence on outcome irrelevant criteria that the experimental context was not executed as planned (e.g., failure of a manipulation check), not because the results are different than desired or deemed unexciting. Detailed treatments of the RR publishing model are available elsewhere (Chambers, 2013; Chambers et al., 2014; Nosek & Lakens, 2014; [http://cos.io/rr/\)](http://cos.io/rr/). The purpose of the present article is to evaluate a common concern of journal editors for adopting the RR publishing format.

</details>

<details><summary>Source [4]: Registered Reports: A New Publishing Initiative at Cortex (https://doi.org/10.1016/j.cortex.2012.12.016)</summary>

This is why we will soon be introducing an additional format of empirical article called a Registered Report. In contrast to the existing publication options at Cortex, which will remain unchanged, the cornerstone of Registered Reports is that a substantial part of each submission will be reviewed prior to data collection. Initial manuscripts will be submitted before a study has been undertaken and will include a slimline introduction, hypotheses, experimental procedures, analysis pipeline, a statistical power analysis, and pilot data where applicable. An initial round of editorial selection will triage the most promising studies for in-depth peer review. Following peer review, the article will then either be rejected or accepted in principle for publication. Once in principle acceptance (IPA) has been obtained, the authors will proceed to conduct the study, adhering exactly to their peer-reviewed procedures. When the study is complete the authors will submit their finalised manuscript for re-review and will publicly share their raw data and laboratory log. Pending quality checks and a sensible interpretation of the findings, the manuscript will be published e and, crucially, independently of what the results show. The Registered Reports format has several attractive characteristics. First, it will be immune to publication bias because the decision to accept or reject manuscripts will be based on the significance of the research question and validity of the methods, never on whether results are novel or statistically significant. Second, by requiring authors to adhere to a preapproved methodology and analysis pipeline, it will instantly prevent a host of questionable but common practices that promote false discoveries, including p value fishing, creative outlier exclusion, and selective reporting of analyses.

</details>

<details><summary>Source [5]: Opening open science to all: Demystifying reproducibility and transparency practices in linguistic research (https://doi.org/10.31234/osf.io/spz4w)</summary>

Registered reports (RRs) represent a new publication model that conceptually combines preregistration with peer review (Nosek & Lakens, 2014). Preregistration is often confused with RRs, but they differ in that preregistration is a separate step that occurs before the traditional publishing pipeline, whereas RR is integrated into the publishing process. In this model, researchers submit a detailed proposal of their study, including their hypotheses, methods, and analyses, for review before data collection. If the proposal is accepted, the study is guaranteed publication, regardless of the results. This incentivizes rigorous methodology and reduces QRPs, as researchers cannot manipulate their analyses to obtain significant results. [Figure](#page-25-0) 3 provides a side-by-side comparison of the standard publishing model and RRs. <span id="page-25-0"></span>*Figure 3: A comparison flow chart of the standard publication model and registered reports.* RRs were first introduced in 2013 by the Center for Open Science (COS), and have since been adopted by many journals across various fields, including psychology, neuroscience, and medicine. In 2019, there were approximately 156 journals offering RRs. This number has jumped to 319 at the time of writing this manuscript, an increase of 104%. Of those 319, only 14 are journals related to language or linguistics. [Table](#page-26-0) 2 lists the language/linguistics journals along with information regarding relevant restrictions.

</details>


## o02

**Question:** How can I get involved with FORRT?

**Category:** FORRT &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the forrt pages

**Judge:** 1.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> To get involved with FORRT, you can join our Slack channel, which is the main hub for our community and where we coordinate our efforts. You can join the Slack channel by clicking on this link: https://join.slack.com/t/forrt/shared_invite/zt-alobr3z7-NOR0mTBfD1vKXn9qlOKqaQ
>
> Additionally, you can check out our "Get Involved" page, which lists various projects and initiatives that you can contribute to. You can find the "Get Involved" page by clicking on this link: https://forrt.org/about/get-involved/
>
> If you're interested in learning more about FORRT and our projects, you can also check out our "Publications" page, which lists our research and publications. You can find the "Publications" page by clicking on this link: https://forrt.org/publications
>
> Finally, you can also reach out to us directly by emailing [info@forrt.org](mailto:info@forrt.org). We're always happy to hear from new people and help them get involved with our community.
>
> [1] [2]

<details><summary>Source [1]: Get Involved (https://forrt.org/about/get-involved/)</summary>

## Get Involved The majority of FORRT’s operations are done via our [Slack channel](https://join.slack.com/t/forrt/shared_invite/zt-alobr3z7-NOR0mTBfD1vKXn9qlOKqaQ). We use Slack to keep everyone up-to-date, to share interesting resources, coordinate FORRT teams, announce FORRT projects, build community, and to provide a platform for ongoing discussions on our projects, organization, and mission. [**You can join FORRT’s Slack here**.](https://join.slack.com/t/forrt/shared_invite/zt-alobr3z7-NOR0mTBfD1vKXn9qlOKqaQ) ## In-depth introduction to FORRT In pursuit of the best conceivable educational practices in higher education If you are looking to a deep dive into FORRT, there are two main ways to learn about us. If you are interested in learning about what we do, check out our [**Publications page**](https://forrt.org/publications). If you want to learn about the intricacies of the FORRT organization, beyond what you can learn from the several pages in our About FORRT pages, and before [joining our Slack](https://join.slack.com/t/forrt/shared_invite/zt-alobr3z7-NOR0mTBfD1vKXn9qlOKqaQ), we prepared a document for you: [**Getting Started with FORRT**](https://docs.google.com/document/d/17ECRs6J8spO3CU6siheGL8weQ-TzdyAUpXIiIE8cUeI). It is organized in terms of involvement with the FORRT organization. - In part (1), we briefly describe general information about FORRT, its Slack channels and community, and provide links to resources; - In part (2), we describe in more detail the current initiatives at FORRT, which would benefit from your help and contribution (with authorship opportunities but no required involvement with the organization per se; - In part (3), we describe the FORRT’s organization, structure, and how to take part in it. Check it out! [**“Getting Started with FORRT”**](https://docs.google.com/document/d/e/2PACX-1vR_OKOxDlrbPcXn6SZLYlq19139ofcYDInBu9E392jWG5yzbp2VjF7E1_fwtzTz4Wxo9i4ddHZTbHfT/pub) ## Ongoing Projects ## Join the movement for better education The projects below are some of the active initiatives where we are looking for collaborators. Most projects coordinate on FORRT’s [Slack](https://join.slack.com/t/forrt/shared_invite/zt-alobr3z7-NOR0mTBfD1vKXn9qlOKqaQ) — join the workspace, then follow the project link or email the contact below to get involved. ### [FLoRA - FORRT Library of Reproduction and Replication Attempts](https://forrt.org/replication-hub/flora/) FLoRA tracks attempts to repeatedly test published findings across the sciences and humanities. As an open, crowd-sourced project we are always looking for collaborators to help curate replications and reproductions and to put the data to use. [Visit project](https://forrt.org/replication-hub/flora/)[Email Lukas Röseler](mailto:lukas.roeseler@uni-muenster.de) ### Lighthouse The FORRT Robustness Lighthouse is building infrastructure to showcase the robustness and reproducibility of the evidence for key effects, and thus to support teaching and research alike. We welcome collaborators interested in metascience, data curation, and tool development. [Email Lukas Röseler](mailto:lukas.roeseler@uni-muenster.de) ### [Best-Practice Guidelines for Psychology](https://forrt.org/best-practices-psychology/) A community-driven initiative developing consensus-based best-practice guidelines for psychology that support the most stringent levels of the TOP Guidelines, covering practices such as preregistration, open data and open materials, with all outputs released under CC-BY for adaptation by other disciplines. Researchers, journals, funders and societies are invited to take part in hackathons, consensus discussions and endorsement activities throughout 2026–2028. [Visit project](https://forrt.org/best-practices-psychology/)[Email Lisa Spitzer](mailto:ls@leibniz-psychology.org) ### [Re-SearchTerms](https://forrt.org/apps/re-searchterms.html) Re-SearchTerms is an interactive app that helps researchers and educators explore open-science terms and their various definitions across multiple sources. We welcome contributors to help expand the database, enrich the app’s features, and refine the interface. [Visit project](https://forrt.org/apps/re-searchterms.html)[Email Anna Leung](mailto:leung.yi.lmu@gmail.com) ### [Mapping Open Science Communities](https://forrt.org/mapping_os/) A global effort to systematically identify, map, and connect Open Science organisations across disciplines and regions. Volunteers help with desk research, taxonomy work, and visualisation. [Visit project](https://forrt.org/mapping_os/) Contact: Flavio Azevedo (reach out via Slack) ### Team Credit Team Credit ensures all contributions to FORRT projects are accurately and appropriately recognised, developing tools and policies that make community work visible. [Slack](https://forrt.slack.com/archives/C082GR7P04X)[Email Ana Marinho](mailto:carolsmarinho.ana@gmail.com) ### Team Outreach Team Outreach disseminates FORRT activities, initiatives and accomplishments through social media, newsletters, and community-facing materials. [Slack](https://forrt.slack.com/archives/C0184989HHC) Contact: Flavio Azevedo (reach out via Slack) ### Feedback Team Feedback is developing a community-maintained e-book mapping and critically evaluating feedback mechanisms across disciplines and regions. [Email Thomas Rhys Evans](mailto:thomas.evans@greenwich.ac.uk) ### [OS Games Portal](https://forrt.org/open-research-games-portal/) A crowdsourced, pedagogically informed database of games and interactive activities for teaching open and reproducible research. We welcome contributions of new games, evaluations, and playing tips. [Visit project](https://forrt.org/open-research-games-portal/)[Email Iris Smal](mailto:games@forrt.org) ### FORRT Storytelling Telling the story of FORRT in a compelling way to preserve the vision, values, struggles, breakthroughs, and relationships that shaped the FORRT’s trajectory. We welcome storytellers, editors, and collaborators interested in narrative methods. [Email Iris Smal](mailto:i.m.smal@uva.nl) ### [Clusters & Curated Resources](https://forrt.org/clusters/) FORRT has a vast collection of open scholarship readings (Clusters) and Curated Resources. Volunteers help review, tag, and recommend resources to make them discoverable and useful. [Visit project](https://forrt.org/clusters/)[Email Lukas Wallrich](mailto:l.wallrich@bbk.ac.uk) ### [JUST-OS Chatbot](https://forrt.org/just_os_chatbot/) JUST-OS is an AI-based chatbot that helps researchers navigate Open Science resources. Collaborators are welcome for work on technical improvements and content curation. [Visit project](https://forrt.org/just_os_chatbot/)[Email Lukas Wallrich](mailto:l.wallrich@bbk.ac.uk) ### Team Website Team Website maintains and improves forrt.org, with content updates, new pages, accessibility, and ideas for showcasing FORRT’s work. [Slack](https://forrt.slack.com/archives/C080N39QRJ9)[Email Lukas Wallrich](mailto:l.wallrich@bbk.ac.uk) ### [Nowhere Lab](https://forrt.org/nowherelab/) Nowhere Lab is an online community for people who would like the lab meeting experience but don’t currently have one. Weekly meetings and an active Slack bring together members across all populated continents and career stages. [Visit project](https://forrt.org/nowherelab/)[Slack](https://forrt.slack.com/archives/C0B0FKG3GH2)[Email Priya Silverstein](mailto:priyasilverstein@gmail.com) ### Team Curriculum Team Curriculum develops open and reproducible lecture materials and supports the integration of principled education into university curricula. Contact: Federica Stablum (reach out via Slack) ## Community calendar This calendar comes from Google Calendar. Loading it sends your IP address to them and they may set cookies. See our [privacy policy](https://forrt.org/privacy/#embedded-content). [Open on the provider's site](https://calendar.google.com/calendar/embed?src=forrtproject%40gmail.com&ctz=Europe%2FBerlin) ## Get in touch Whether you have questions getting started or you want to know how to best integrate FORRT features into your workflow, we’re here to help you. ### Email [info@forrt.org](mailto:info@forrt.org) ### Slack [Join our open Slack channel](https://join.slack.com/t/forrt/shared_invite/enQtODMwODI0OTk4ODgzLTM0ZTQ3NDk5MzA1ZjBmNWJjYTVlN2Y2YTk0ZTJhYTY5NDliMDYzMjg2MWE0ZDRhOTY0ZDY3OTRlNDA4ODQ3NjQ) ### GitHub [Join our team on GitHub](https://github.com/forrtproject) ## Stay updated Subscribe to our newsletter from FORRT to get the latest news about our initiatives. JUST-OS

</details>

<details><summary>Source [2]: Updated Get Involved page (https://forrt.org/post/2026-05-get-involved-page/)</summary>

# Updated Get Involved page [FORRT](https://forrt.org/authors/forrt/) Last updated on Jul 2, 2026 1 min read [Resource](https://forrt.org/category/resource/) The **Get Involved** page has been updated and rebuilt, and we have made it easier to keep the updates coming. So if you are looking for ways to get involved, have a look at the current opportunities now. [Get involved](https://forrt.org/about/get-involved/) ##### [FORRT](https://forrt.org/authors/forrt/) - - - - [Next JUST-OS chatbot launched to help navigate Open Science resources](https://forrt.org/post/2026-05-just-os-chatbot/) [Previous FORRT Newsletter — April 2026](https://forrt.org/post/2026-04-newsletter/) ### Related - [FORRT at BTSCON2026](https://forrt.org/post/2026-10-presentations/) - [Catch up with the AI in Metascience conference talks](https://forrt.org/post/2026-10-ai-in-metascience-recordings/) - [Chinese-language Glossary of Open Scholarship terms](https://forrt.org/post/2026-05-chinese-glossary/) - [Nowhere Lab: an online community for those without a lab](https://forrt.org/post/2026-05-nowhere-lab/) - [JUST-OS chatbot launched to help navigate Open Science resources](https://forrt.org/post/2026-05-just-os-chatbot/) JUST-OS

</details>


## o06

**Question:** Who is on FORRT's steering committee?

**Category:** FORRT &nbsp; **The bot should:** answer &nbsp; **The bot:** answered from the forrt pages

**Judge:** 1.0 &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> The FORRT Steering Committee is composed of several teams, each with its own director and deputy directors. The teams are:
>
> * Community & Sustainability, led by Dr. Steven Verheyen and Adira Daniel [1]
> * Social Justice & DEIA, led by Dr. Sarah A. Sauvé [1]
> * Meta-science & Research, led by Dr. Rachel Heyard and Dr. Tom Heyman [1]
> * Education & Pedagogy, led by Dr. Madeleine Pownall and Prof. Lorna Hamilton [1]
> * Operations & Stewardship, led by Dr. Amanda Kay Montoya and Dr. Kelly Lloyd [1]
> * Community Engagement, led by Dr. Lukas Röseler [1]
> * Sustainability & Strategy, led by Dr. Sarah Ashcroft-Jones and Dr. Sara Lil Middleton [1]
> * Ethics and Inclusion, led by Dr. John Shaw and Ruth Van der Hallen, PhD [1]
> * Fundraising, led by Dr. Max Korbmacher and Karen Matvienko-Sikar [1]
> * Financial Transparency, led by Alicia Tamara Veersma Barredo [1]
> * Partnerships, led by Adam Partridge [1]
> * Digital Infrastructure Team, led by Justin Sulik and Dushime Mudahera Richard [1]
> * Communication, Dissemination & Impact, led by Charlotte Pennington [1]
> * FORRT Stewards, led by Ana Carolina Marinho, Stephanie Zellers, Roksana Sobolak, Riva Quiroga, and Meera Chandra [1]
> * Strategic Facilitation & Integration, led by Dr. Lukas Wallrich and Dr. Flavio Azevedo [1]
> * Guidance & Oversight, led by Sam Parsons, Thomas Rhys Evans, and Ruth Van der Hallen, PhD [1]
>
> You can find more information about the Steering Committee on the [Steering Committee](https://forrt.org/about/steering-committee/) page.

<details><summary>Source [1]: Steering Committee (https://forrt.org/about/steering-committee/)</summary>

Strategic Focus Areas Core mission-driven teams advancing open scholarship, social justice, and community sustainability. Team ### Community & Sustainability #### dr. Steven Verheyen Director #### Adira Daniel Co-Director Team ### Social Justice & DEIA #### Dr. Sarah A. Sauvé Director Team ### Meta-science & Research #### Dr Rachel Heyard Director #### Dr. Tom Heyman Deputy-Director #### Berit T. Barthelmes, M.Sc. Project Manager Team ### Education & Pedagogy #### Dr Madeleine Pownall Director #### Prof Lorna Hamilton Deputy-Director Operations & Stewardship Infrastructure, community management, ethical oversight, and support systems powering FORRT. Team ### Community Governance & Management #### Dr. Amanda Kay Montoya Director #### Dr Kelly Lloyd Cohesion-Liaison #### Giorgia Andreolli Cohesion-Liaison Team ### Community Engagement #### Dr. Lukas Röseler Infrastructure-Liaison Team ### Sustainability & Strategy #### Dr Sarah Ashcroft-Jones Director #### Dr Sara Lil Middleton Knowledge Manager Team ### Ethics and Inclusion #### Dr John Shaw Director #### Ruth Van der Hallen, PhD Confidential Advisor #### Thomas Rhys Evans Advisor Team ### Fundraising #### Dr Max Korbmacher Director #### Karen Matvienko-Sikar Co-Director #### Fotis Mystakopoulos, PhD Student Officer Team ### Financial Transparency #### Alicia Tamara Veersma Barredo Officer Team ### Partnerships #### Adam Partridge Director Team ### Digital Infrastructure Team #### Justin Sulik Director #### Dushime Mudahera Richard Website Lead Team ### Communication, Dissemination & Impact #### Charlotte Pennington Director Team ### FORRT Stewards #### Ana Carolina Marinho FORRT Steward #### Stephanie Zellers FORRT Steward #### Roksana Sobolak FORRT Steward #### Riva Quiroga FORRT Steward #### Meera Chandra FORRT Steward Strategic Facilitation & Integration Synthesising community efforts to maintain alignment with FORRT’s mission and vision. #### Dr Lukas Wallrich Co-Director #### Dr Flavio Azevedo Director Guidance & Oversight Independent ethical guidance and long-term stewardship. To raise a concern or talk something through in confidence, see our [Confidential Advisor & Ombuds](https://forrt.org/about/confidential-advisor-ombuds/) page. #### Sam Parsons Stewardship Panel #### Thomas Rhys Evans Ombuds #### Ruth Van der Hallen, PhD Confidential Advisor

</details>


## off15

**Question:** What is photosynthesis?

**Category:** should be refused (science-related) &nbsp; **The bot should:** refuse &nbsp; **The bot:** refused

**Judge:** – &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> (no answer)


## rf32

**Question:** APC for Nature Communications

**Category:** should be refused (science-related) &nbsp; **The bot should:** refuse &nbsp; **The bot:** said it found no sources

**Judge:** – &nbsp; **Your score:** ____ &nbsp; **Note:**

**Answer**

> (no answer)

