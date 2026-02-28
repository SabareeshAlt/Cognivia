/**
 * AcademeRAG Frontend API Client
 * Handles communication with Django backend
 */

class RAGClient {
  constructor(baseUrl = window.location.origin) {
    this.baseUrl = baseUrl;
    this.apiEndpoint = `${baseUrl}/api`;
  }

  /**
   * Ask a question and get a response
   * @param {string} question - The question to ask
   * @returns {Promise<Object>} - The response containing answer and sources
   */
  async askQuestion(question) {
    if (!question || question.trim().length === 0) {
      throw new Error("Question cannot be empty");
    }

    try {
      const response = await fetch(`${this.apiEndpoint}/ask/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.statusText}`);
      }

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || "Unknown error occurred");
      }

      return data;
    } catch (error) {
      console.error("API Error:", error);
      throw error;
    }
  }

  /**
   * Stream an answer using Server-Sent Events
   * @param {string} question - The question to ask
   * @param {Function} onChunk - Callback for each chunk received
   * @param {Function} onComplete - Callback when streaming is complete
   * @param {Function} onError - Callback for errors
   */
  streamAnswer(question, onChunk, onComplete, onError) {
    if (!question || question.trim().length === 0) {
      onError("Question cannot be empty");
      return;
    }

    try {
      fetch(`${this.apiEndpoint}/stream/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question }),
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error(`Server error: ${response.statusText}`);
          }
          return response;
        })
        .then((response) => {
          const reader = response.body.getReader();
          const decoder = new TextDecoder();

          const readStream = () => {
            reader.read().then(({ done, value }) => {
              if (done) {
                onComplete();
                return;
              }

              const chunk = decoder.decode(value);
              const lines = chunk.split("\n");

              lines.forEach((line) => {
                if (line.startsWith("data: ")) {
                  try {
                    const data = JSON.parse(line.substring(6));
                    onChunk(data);
                  } catch (e) {
                    console.error("Error parsing SSE data:", e);
                  }
                }
              });

              readStream();
            });
          };

          readStream();
        })
        .catch(onError);
    } catch (error) {
      onError(error.message);
    }
  }

  /**
   * Check API health
   * @returns {Promise<Object>} - Health status
   */
  async healthCheck() {
    try {
      const response = await fetch(`${this.apiEndpoint}/health/`);
      if (!response.ok) {
        throw new Error(`Server error: ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      console.error("Health check error:", error);
      throw error;
    }
  }

  /**
   * Get model information
   * @returns {Promise<Object>} - Model details
   */
  async getModelInfo() {
    try {
      const response = await fetch(`${this.apiEndpoint}/model-info/`);
      if (!response.ok) {
        throw new Error(`Server error: ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      console.error("Model info error:", error);
      throw error;
    }
  }
}

// Export for use in HTML
window.RAGClient = RAGClient;

// Example usage in Final.html:
/*
const ragClient = new RAGClient();

// Using the ask endpoint
try {
  const result = await ragClient.askQuestion("What is Django?");
  console.log("Answer:", result.answer);
  console.log("Sources:", result.sources);
} catch (error) {
  console.error("Failed to ask question:", error);
}

// Using the streaming endpoint
ragClient.streamAnswer(
  "What is Django?",
  (data) => {
    console.log("Chunk:", data);
  },
  () => {
    console.log("Streaming complete");
  },
  (error) => {
    console.error("Streaming error:", error);
  }
);
*/
