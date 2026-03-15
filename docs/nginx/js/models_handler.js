function handleModels(r) {
    // Log the request
    r.log("Handling /v1/models request");

    // Define the static response
    let modelsResponse = {
        data: [
            {
                id: "llama3",
                object: "model",
                connection_type: "external",
                name: "llama3",
                owned_by: "openai",
                openai: {
                    id: "llama3",
                    object: "model",
                    connection_type: "external"
                },
                urlIdx: 0,
                actions: [],
                filters: [],
                tags: []
            }
        ]
    };

    // Log the response details
    r.log("Returning static models response, model count: " + modelsResponse.data.length);
    r.log("Models response: " + JSON.stringify(modelsResponse));

    // Return the static response
    r.return(200, JSON.stringify(modelsResponse));
}

export default { handleModels };