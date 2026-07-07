# AcademeRAG Evaluation Failure Reports

## Failure case 1 (ID: factual_1)
- **Category**: Unknown
- **Question**: What are the subjects taught in the BE Computer Science and Engineering programme?
- **Expected**: Expected sources: ['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf'], Keywords: ['computer science', 'engineering', 'subject', 'course']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 0.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: Unable to generate explanation.

## Failure case 2 (ID: syllabus_1)
- **Category**: Retrieval Failure
- **Question**: What is the syllabus for the first unit of any subject in the provided documents?
- **Expected**: Expected sources: ['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf'], Keywords: ['unit', 'introduction', 'topics', 'hours']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 0.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The system failed because no relevant context regarding syllabi was retrieved from the source documents, resulting in all context metrics scoring 0.0. Although the generated answer correctly stated that the information was missing, the root cause of the failure is poor retrieval performance.

## Failure case 3 (ID: keyword_1)
- **Category**: Retrieval Failure
- **Question**: What topics are covered under data structures in the syllabus?
- **Expected**: Expected sources: ['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf'], Keywords: ['data structures', 'array', 'linked list', 'tree', 'stack']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 1.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The system failed to retrieve any relevant context regarding data structures topics from the source documents, resulting in a complete lack of information for the model to use. This failure occurred entirely within the retrieval stage.

## Failure case 4 (ID: summary_1)
- **Category**: Retrieval Failure
- **Question**: Summarize the contents of the first document.
- **Expected**: Expected sources: ['RAG sample 1.pdf'], Keywords: ['subject', 'unit', 'total', 'periods']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 1.0, Relevancy: 1.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The system failed to retrieve any relevant context (the first document) needed to fulfill the summarization request. Consequently, the generation step correctly reported that no information was available for answering the question.

## Failure case 5 (ID: negative_1)
- **Category**: Generation Hallucination
- **Question**: What is the capital of France?
- **Expected**: Expected sources: [], Keywords: ['not found in the provided documents']
- **Retrieved Context**: 
```
{% localtime on %}
{{ value }}
{% endlocaltime %}
{% localtime off %}
{{ value }}
{% endlocaltime %}
® Note
The value of USE_TZ isn’t respected inside of a {% localtime %} block.
timezone
Sets or unsets the current time zone in the contained block. When the current time zone is unset, the default
time zone applies.
{% load tz %}
{% timezone "Europe/Paris" %}
Paris time: {{ value }}
{% endtimezone %}
(continues on next page)
3.16.
Internationalization and localization
719

Django Documentation, R...
```
- **Generated Answer**: 
```
Based on the available documents, the capital of France is not stated as a direct geographical fact. However, the concept appears within an example describing how symbolic properties and relations between entities can be matched, using the following structure:

“Rome” −“Italy” + “France” = “Paris” [Source: RAG sample 2.pdf, Page 56].
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 0.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The retrieved context was entirely irrelevant to the question, containing only Django documentation on time zones. Despite this lack of information, the model hallucinated a specific example ("Rome" −“Italy” + “France” = “Paris”) and fabricated a source citation that is not supported by the provided text or any factual knowledge.

## Failure case 6 (ID: multipage_1)
- **Category**: Retrieval Failure
- **Question**: What is the total number of periods or lecture hours specified across all units in any subject?
- **Expected**: Expected sources: ['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf'], Keywords: ['total', 'periods', 'hours', 'unit']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 1.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The system correctly determined it could not answer, but this failure stems from insufficient context retrieval; the necessary data points required for a comprehensive summation across all units were missing or too fragmented in the retrieved documents.

## Failure case 7 (ID: table_1)
- **Category**: Retrieval Failure
- **Question**: List all the units and their titles as mentioned in the documents.
- **Expected**: Expected sources: ['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf'], Keywords: ['unit', 'title', 'introduction']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 1.0, Relevancy: 1.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The system correctly determined that the information was missing, but the low Context Recall and Context Precision scores indicate a fundamental failure in the retrieval step. Relevant source material containing the units and titles was not successfully retrieved and provided to the generation model.

## Failure case 8 (ID: semantic_1)
- **Category**: Retrieval Failure
- **Question**: What programming languages or tools are mentioned in the curriculum?
- **Expected**: Expected sources: ['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf'], Keywords: ['language', 'tool', 'programming', 'software']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 1.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The low Context Recall and Context Precision scores indicate that the system failed to retrieve any relevant documents containing information about programming languages or tools mentioned in the curriculum.

## Failure case 9 (ID: gen_1)
- **Category**: Generation Hallucination
- **Question**: State Newton's first law of motion and explain the concept of inertia.
- **Expected**: Expected sources: ['RAG sample 1.pdf'], Keywords: ['Newton', 'first law', 'inertia']
- **Retrieved Context**: 
```
acceleration. Newton’s first law is often called the law of inertia. As we know from experience, some objects have 
more inertia than others. It is more difficult to change the motion of a large boulder than that of a basketball, for 
example, because the boulder has more mass than the basketball. In other words, the inertia of an object is 
measured by its mass. The relationship between mass and weight is explored later in this chapter. 
Inertial Reference Frames 
Earlier, we stated Newton’s fi...
```
- **Generated Answer**: 
```
### Newton's First Law of Motion

Newton's first law describes how an object maintains its state of motion unless acted upon by external forces. The law can be stated in several ways:

1. A body at rest remains at rest, or if it is already in motion, it remains in motion at a constant velocity unless acted on by a net external force .
2. Alternatively, the law states that every body remains in its state of uniform motion in a straight line unless compelled to change that state by forces acting on it .

The physical implication of this law is that if the net force ($\vec{F}_{\text{net}}$) acting on an object is zero, the object's velocity remains constant (meaning its path is a straight line and both its magnitude and direction are unchanged) .

Mathematically, this concept of net external force is represented by Equation 5.1:

$$\vec{F}_{\text{net}} = \sum \vec{F} = \vec{F}_1 + \vec{F}_2 + \cdots$$

***

### The Concept of Inertia

Inertia is the property of an object that describes its resistance to changes in motion—that is, its resistance to acceleration .

* **Relationship to Mass:** Inertia is directly measured by an object's mass . The documents explain that objects with more mass possess more inertia; for example, it is more difficult to change the motion of a large boulder than a basketball because the boulder has greater mass .
* **The Law of Inertia:** Newton's first law is often referred to as the law of inertia because it quantifies this resistance to change in motion .
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 1.0, Recall: 1.0, Precision: 1.00
- **Judge Explanation**: The system failed because it introduced specific mathematical details, such as "Equation 5.1" and the formula $\vec{F}_{\text{net}} = \sum \vec{F}$, which were not present in the retrieved context. This demonstrates a hallucination of external, technical knowledge rather than relying solely on the provided source material.

## Failure case 10 (ID: syllabus_2)
- **Category**: Retrieval Failure
- **Question**: List the course objectives mentioned in the documents.
- **Expected**: Expected sources: ['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf'], Keywords: ['objective', 'student', 'understand', 'course']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 1.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The system failed because the retriever could not identify or pull the relevant document sections containing the course objectives, resulting in a lack of context for the generation model.

## Failure case 11 (ID: keyword_2)
- **Category**: Retrieval Failure
- **Question**: What does the syllabus say about operating systems?
- **Expected**: Expected sources: ['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf'], Keywords: ['operating system', 'process', 'scheduling', 'memory']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 1.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The system failed because the necessary information regarding operating systems was not successfully retrieved from the source documents, leading the model to correctly report that the answer could not be found.

## Failure case 12 (ID: summary_2)
- **Category**: Retrieval Failure
- **Question**: Give a brief overview of the academic content in the provided PDF documents.
- **Expected**: Expected sources: ['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf'], Keywords: ['syllabus', 'course', 'unit', 'engineering']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 1.0, Relevancy: 0.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The system failed because it could not retrieve or utilize the necessary academic content from the provided documents, leading to an inability to generate the requested overview.

## Failure case 13 (ID: negative_2)
- **Category**: Retrieval Failure
- **Question**: Who won the FIFA World Cup in 2022?
- **Expected**: Expected sources: [], Keywords: ['not found in the provided documents']
- **Retrieved Context**: 
```
...
```
- **Generated Answer**: 
```
Not found in the provided documents.
```
- **Metrics**: Faithfulness: 1.0, Relevancy: 0.0, Recall: 0.0, Precision: 0.00
- **Judge Explanation**: The system failed because it could not retrieve any relevant context containing the factual answer, resulting in a negative rejection instead of providing the requested information.

## Failure case 14 (ID: gen_13)
- **Category**: Generation Hallucination
- **Question**: How does the conservation of energy apply to a simple pendulum at its maximum displacement?
- **Expected**: Expected sources: ['RAG sample 1.pdf'], Keywords: ['conservation of energy', 'pendulum', 'displacement']
- **Retrieved Context**: 
```
doing work, then mechanical energy is not conserved. The system must then be analyzed with non-
conservative work, Equation 8.12. 
4. For every conservative force that does work, choose a reference point and determine the potential energy 
function for the force. The reference points for the various potential energies do not have to be at the same 
location. 
5. If no non-conservative work is done, apply the principle of mechanical energy conservation by setting the sum 
of the kinetic energies ...
```
- **Generated Answer**: 
```
The conservation of energy principle dictates that at the maximum displacement (the highest point) of a simple pendulum, the system's total mechanical energy is entirely potential energy, and its kinetic energy is zero.

### Energy Components at Maximum Displacement

When the pendulum reaches its maximum displacement:

1. **Kinetic Energy ($K$):** The particle momentarily comes to rest before changing direction. Therefore, the rotational (or linear) velocity is zero, meaning the kinetic energy is zero .
2. **Potential Energy ($U$):** Since this point represents the greatest vertical height relative to the lowest point of the swing, the gravitational potential energy is at its maximum value [Source: RAG sample 1.pdf, Page 496].

### Application of Conservation of Energy

The principle of mechanical energy conservation states that the sum of kinetic and potential energies remains constant throughout the motion (assuming no non-conservative forces like air resistance are acting) [Source: RAG sample 1.pdf, Page 367]:

$$E_{initial} = E_{final}$$

At maximum displacement (the initial point), the total energy ($E$) is equal to the potential energy at that height ($U_{max}$):

$$E = K + U \implies E = 0 + U_{max} = U_{max}$$

This value, $U_{max}$, must be conserved and therefore equals the total energy at any other point in the swing (e.g., the lowest point). At the lowest point of the swing, where potential energy is defined as zero, all of this initial potential energy has been converted into kinetic energy ($K_{max}$), such that:

$$U_{max} = K_{max}$$

This relationship allows one to calculate the speed at the bottom of the arc by equating the maximum potential energy (at max displacement) to the maximum kinetic energy (at lowest point) .
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 1.0, Recall: 1.0, Precision: 1.00
- **Judge Explanation**: The system failed because although the generated answer was highly relevant and accurate, it provided a detailed theoretical explanation that synthesized external physics knowledge (the full conservation principle applied to max displacement). This level of deep synthesis exceeded the direct scope of the retrieved context snippets, causing the evaluator to mark the output as unfaithful.

## Failure case 15 (ID: gen_16)
- **Category**: Generation Hallucination
- **Question**: What are the standard SI base units for mass, length, and time?
- **Expected**: Expected sources: ['RAG sample 1.pdf'], Keywords: ['SI base units', 'kilogram', 'meter', 'second']
- **Retrieved Context**: 
```
track which phenomena occur on which scales. 
They also use orders of magnitude to compare 
the various scales. 
• Scientists attempt to describe the world by 
formulating models, theories, and laws. 
1.2 Units and Standards 
• Systems of units are built up from a small 
number of base units, which are defined by 
accurate and precise measurements of 
conventionally chosen base quantities. Other 
units are then derived as algebraic combinations 
of the base units. 
• Two commonly used systems of...
```
- **Generated Answer**: 
```
The standard SI base units for length, mass, and time are as follows:

* **Length:** meter ($\text{m}$) [Source: RAG sample 1.pdf, Page: 46]
* **Mass:** kilogram ($\text{kg}$) [Source: RAG sample 1.pdf, Page: 46]
* **Time:** second ($\text{s}$) [Source: RAG sample 1.pdf, Page: 46]

These units are part of the International System of Quantities (ISQ) and form the basis for all other physical quantities in the SI system [Source: RAG sample 1.pdf, Page: 25].
```
- **Metrics**: Faithfulness: 0.0, Relevancy: 1.0, Recall: 1.0, Precision: 0.75
- **Judge Explanation**: Although the model correctly extracted the core answer from the context, it added supplementary explanatory text ("These units are part of the International System of Quantities...") that was not explicitly detailed or supported by the retrieved passage, causing a failure in faithfulness.
